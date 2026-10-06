"""Durable campaign workflow: the autonomous propose-run-judge loop.

Each iteration proposes an edit, commits it, runs one job, then keeps the
commit or resets to the parent. Stop conditions are checked at the top of
the loop in precedence order; the signal name for cancel is ``cancel``.
"""

from pathlib import Path

from dbos import DBOS
from pydantic_ai.exceptions import AgentRunError

from ..executor import JobInfo
from ..schema.events import Actor, Event, EventType, StopReason
from ..schema.plan import resolve_target_in_repo
from .models import CampaignSetup, ExperimentSetup, Proposal
from .proposer import ExperimentProposer
from .runtime import Runtime
from .tree import CommitResult, commit_file, reset_hard

# Consecutive propose-step failures that end the campaign
MAX_PROP_FAILS = 5


def _gpu_hours(info: JobInfo, gpus: int) -> float:
    """GPU-hours burned by one terminal job"""
    sec = info.elapsed_seconds
    assert sec is not None
    return sec * gpus / 3600.0


@DBOS.dbos_class()
class CampaignRunner:
    """Owns the durable campaign loop on top of a Runtime."""

    def __init__(
        self,
        runtime: Runtime,
        proposer: ExperimentProposer,
        gpus: int = 1,
    ) -> None:
        self.runtime = runtime
        self.config_name = runtime.config_name
        self.proposer = proposer
        self.gpus = gpus

    # -- steps (checkpointed; replayed without re-execution) --

    @DBOS.step()
    def propose_step(self, setup: CampaignSetup, current: str) -> Proposal:
        """Ask the proposer for one replacement."""
        return self.proposer.propose(setup.campaign_id, setup.plan, current)

    @DBOS.step()
    def commit_step(self, repo: Path, target_file: str, message: str) -> CommitResult:
        """Commit the proposed edit to the target repo."""
        return commit_file(repo, target_file, message)

    @DBOS.step()
    def discard_step(self, repo: Path, parent_sha: str) -> None:
        """Revert the working tree to the parent commit."""
        reset_hard(repo, parent_sha)

    @DBOS.step()
    def read_target_step(self, repo: Path, target_file: str) -> str:
        """Read the current target file content."""
        return (repo / target_file).read_text()

    @DBOS.step()
    def write_target_step(self, repo: Path, target_file: str, content: str) -> None:
        """Write the proposed content to the target file.

        The target must stay inside the repo; the API checks this at
        campaign creation, and the step re-checks as defense in depth.
        """
        resolved = resolve_target_in_repo(str(repo), target_file)
        resolved.write_text(content)

    @DBOS.transaction()
    def record_event(self, event: Event) -> None:
        """Append one event to the ledger within the DBOS transaction."""
        self.runtime.ledger.append_with_session(DBOS.sql_session, event)

    # -- workflow --

    @DBOS.workflow()
    def run_campaign(self, setup: CampaignSetup) -> str:
        """Run the campaign loop until a stop condition fires.

        Returns the stop reason.
        """
        plan = setup.plan
        repo = Path(setup.repo_path)
        exp_done = 0
        gpu_h = 0.0
        best_metric: float | None = None
        prop_fails = 0

        try:
            while True:
                # One check site, in precedence order: cancel, budget, cap.
                if self._cancel_received():
                    reason = StopReason.CANCELLED
                    self._end(setup, reason, exp_done, gpu_h, actor=Actor.HUMAN)
                    return reason.value
                if gpu_h >= plan.budget_gpu_hours and exp_done > 0:
                    self._end(setup, StopReason.BUDGET_EXHAUSTED, exp_done, gpu_h)
                    return StopReason.BUDGET_EXHAUSTED.value
                if exp_done >= plan.max_experiments:
                    self._end(setup, StopReason.MAX_EXPERIMENTS, exp_done, gpu_h)
                    return StopReason.MAX_EXPERIMENTS.value

                current = self.read_target_step(repo, plan.target_file)
                self._record_designing(setup)
                try:
                    proposal = self.propose_step(setup, current)
                except (TimeoutError, AgentRunError) as e:
                    # AgentRunError covers recoverable model-side failures.
                    # Record a failed proposal, then loop back.
                    # Stop looping after max consecutive propose failures.
                    self._record_propose_failure(setup, e)
                    prop_fails += 1
                    if prop_fails >= MAX_PROP_FAILS:
                        self._end(setup, StopReason.ERROR, exp_done, gpu_h)
                        return StopReason.ERROR.value
                    continue
                # From here on, we know the propose step succeeded
                prop_fails = 0
                exp_done += 1
                self.write_target_step(repo, plan.target_file, proposal.content)
                commit_msg = f"exp {exp_done}: {proposal.title}"
                result = self.commit_step(repo, plan.target_file, commit_msg)
                self._record_proposal(setup, exp_done, result, proposal)

                exp = ExperimentSetup(
                    campaign_id=setup.campaign_id,
                    command=plan.command,
                    submission_key=f"{setup.campaign_id}:{exp_done}",
                    metric=plan.metric,
                    repo_path=setup.repo_path,
                    baseline=best_metric if best_metric is not None else plan.baseline,
                    poll_interval_seconds=setup.poll_interval_seconds,
                    walltime=plan.walltime,
                    index=exp_done,
                    sha=result.sha,
                )
                outcome = self.runtime.run_experiment(exp)

                if outcome.job_info.state.is_terminal:
                    gpu_h += _gpu_hours(outcome.job_info, self.gpus)
                if outcome.judgment == "keep":
                    best_metric = outcome.metric_value
                else:
                    self.discard_step(repo, result.parent_sha)
        except Exception as e:
            # Record the crash, then let the workflow fail so DBOS marks it ERROR
            self._record_crash(setup, e)
            self._end(setup, StopReason.ERROR, exp_done, gpu_h)
            raise

    # -- helpers --

    def _cancel_received(self) -> bool:
        """Non-blocking check of the cancel signal."""
        # a time-out would return None
        return DBOS.recv(topic="cancel", timeout_seconds=0.0) is not None

    def _record_propose_failure(self, setup: CampaignSetup, error: Exception) -> None:
        """Record a failed propose event"""
        self.record_event(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_PROPOSE_FAILED,
                reason=f"propose step failed: {error}",
                payload={"error": type(error).__name__},
            )
        )

    def _record_crash(self, setup: CampaignSetup, error: Exception) -> None:
        """Record an unhandled loop exception that ends the campaign."""
        self.record_event(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.CAMPAIGN_CRASHED,
                reason=f"campaign crashed: {type(error).__name__}: {error}",
                payload={"error": type(error).__name__},
            )
        )

    def _record_designing(self, setup: CampaignSetup) -> None:
        """Record the start of the experiment design phase"""
        self.record_event(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_DESIGNING,
                reason="designing the next experiment",
            )
        )

    def _record_proposal(
        self,
        setup: CampaignSetup,
        index: int,
        result: CommitResult,
        proposal: Proposal,
    ) -> None:
        """Record a proper experiment proposal"""
        self.record_event(
            Event(
                campaign_id=setup.campaign_id,
                actor=Actor.AGENT,
                type=EventType.EXPERIMENT_PROPOSED,
                reason=proposal.title,
                payload={
                    "rationale": proposal.rationale,
                    "sha": result.sha,
                    "parent_sha": result.parent_sha,
                    "index": index,
                },
            )
        )

    def _end(
        self,
        setup: CampaignSetup,
        reason: StopReason,
        exp_done: int,
        gpu_h: float,
        actor: Actor = Actor.AGENT,
    ) -> None:
        """Record the campaign-end event."""
        self.record_event(
            Event(
                campaign_id=setup.campaign_id,
                actor=actor,
                type=EventType.CAMPAIGN_ENDED,
                reason=f"campaign ended: {reason.value}",
                payload={
                    "stop_reason": reason,
                    "experiments_done": exp_done,
                    "gpu_hours_burned": gpu_h,
                },
            )
        )
