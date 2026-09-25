"""Pydantic AI proposer for single-file experiments."""

import ast
import contextvars
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model, infer_model
from pydantic_ai.settings import ModelSettings

from ..schema.events import Event
from ..schema.plan import ResearchPlan
from .models import Proposal

# Default proposer timeout (seconds). Overridable with FABERON_PROPOSER_TIMEOUT
DEFAULT_TIMEOUT = 600.0


class CampaignEventReader(Protocol):
    """Source of campaign events for proposer context."""

    def campaign_events(self, campaign_id: UUID) -> list[Event]: ...


class ExperimentProposer(Protocol):
    """Produces one validated replacement for the target file."""

    def propose(
        self,
        campaign_id: UUID,
        plan: ResearchPlan,
        current_content: str,
    ) -> Proposal: ...


@dataclass
class ProposalContext:
    """Everything the proposer's tools need for one proposal."""

    events: CampaignEventReader
    campaign_id: UUID
    current_content: str


class AgentProposer:
    """Runs the experiment proposer against the configured model."""

    _prompt = (
        "Propose one focused ML experiment. Read the target file and the "
        "campaign history before deciding. Return the complete replacement "
        "file and a concise rationale. Start the rationale with a one-line "
        "summary of the change, at most 55 characters; it becomes the git "
        "commit message. The replacement must differ from the current file."
    )

    def __init__(
        self,
        events: CampaignEventReader,
        model: Model,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._events = events
        self._model = model
        self._timeout = timeout
        self._agent: Agent[ProposalContext, Proposal] = Agent(
            deps_type=ProposalContext,
            output_type=Proposal,
            instructions=self._prompt,
        )

        @self._agent.tool
        def read_target_file(ctx: RunContext[ProposalContext]) -> str:
            """Return the current target file."""
            return ctx.deps.current_content

        @self._agent.tool
        def read_experiment_history(ctx: RunContext[ProposalContext]) -> list[Event]:
            """Return every event of this campaign, oldest first."""
            return ctx.deps.events.campaign_events(ctx.deps.campaign_id)

        @self._agent.output_validator
        def validate_content(
            ctx: RunContext[ProposalContext], proposal: Proposal
        ) -> Proposal:
            if proposal.content == ctx.deps.current_content:
                raise ModelRetry("The replacement must change the target file.")
            try:
                ast.parse(proposal.content)
            except SyntaxError as e:
                raise ModelRetry(f"The replacement is not valid Python: {e}") from e
            return proposal

    @classmethod
    def from_env(cls, events: CampaignEventReader) -> AgentProposer:
        """Build a proposer from ``FABERON_MODEL``, resolved at startup."""
        name = os.environ.get("FABERON_MODEL", "").strip()
        if not name:
            raise RuntimeError("FABERON_MODEL is not set")
        timeout = float(os.environ.get("FABERON_PROPOSER_TIMEOUT", DEFAULT_TIMEOUT))
        return cls(events, infer_model(name), timeout=timeout)

    def propose(
        self,
        campaign_id: UUID,
        plan: ResearchPlan,
        current_content: str,
    ) -> Proposal:
        """Propose one replacement using the plan and current campaign state.

        Raises ``TimeoutError`` after ``timeout`` seconds.
        """
        prompt = (
            f"Goal: {plan.goal}\n"
            f"Metric: {plan.metric_name} (lower is better)\n"
            "Current train.py:\n"
            "<target_file>\n"
            f"{current_content}\n"
            "</target_file>"
        )
        # Two layers of timeout.
        # 1. Via the model client's HTTP request (some providers ignore it)
        # 2. _run_with_timeout raises TimeoutError on expiry
        # A timed-out call keeps running on the daemon thread until its HTTP layer gives
        # up, but never blocks the caller or process shutdown.
        return _run_with_timeout(
            self._timeout,
            lambda: (
                self._agent.run_sync(
                    prompt,
                    model=self._model,
                    model_settings=ModelSettings(timeout=self._timeout),
                    deps=ProposalContext(
                        events=self._events,
                        campaign_id=campaign_id,
                        current_content=current_content,
                    ),
                ).output
            ),
        )


def _run_with_timeout(timeout: float, call: Callable[[], Proposal]) -> Proposal:
    """Run the call on a daemon thread, returning its result within the bound.

    Raises ``TimeoutError`` on expiry. Re-raises any exception the call
    raised. The thread is a daemon, so a call that outlives the timeout does
    not block process shutdown.
    """
    result: list[Proposal] = []
    error: list[BaseException] = []
    # Propagate context to the worker thread
    ctx = contextvars.copy_context()

    def target() -> None:
        try:
            result.append(ctx.run(call))
        except BaseException as e:  # propagate to the joining thread
            error.append(e)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"proposer call exceeded {timeout} seconds")
    if error:
        raise error[0]
    return result[0]
