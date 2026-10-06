"""Pydantic AI proposer for single-file experiments."""

import ast
import asyncio
import contextvars
import os
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import TimeoutError as FuturesTimeoutError
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
    """Runs the experiment proposer against the configured model.

    All agent runs execute on one dedicated worker loop. Creating the
    proposer starts the thread; call ``close()`` at shutdown.
    """

    _prompt = (
        "Propose one focused ML experiment. Read the target file and the "
        "campaign history before deciding. Return the complete replacement "
        "file, a title, and a rationale. The title is a one-line summary of "
        "the change, at most 55 characters; it becomes the git commit "
        "message. The rationale is a paragraph explaining the hypothesis, "
        "what changed relative to prior runs, and what each outcome would "
        "tell us. The replacement must differ from the current file."
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
        self._loop = _ProposerLoop()
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
            f"Metric: {plan.metric} (lower is better)\n"
            "Current train.py:\n"
            "<target_file>\n"
            f"{current_content}\n"
            "</target_file>"
        )
        # Two layers of timeout.
        # 1. Via the model client's HTTP request (some providers ignore it)
        # 2. _run_with_timeout cancels the run and raises TimeoutError
        result = _run_with_timeout(
            self._loop,
            self._timeout,
            lambda: self._agent.run(
                prompt,
                model=self._model,
                model_settings=ModelSettings(timeout=self._timeout),
                deps=ProposalContext(
                    events=self._events,
                    campaign_id=campaign_id,
                    current_content=current_content,
                ),
            ),
        )
        return result.output

    def close(self) -> None:
        """Shut the worker loop down. The proposer must not be used after."""
        self._loop.close()


class _ProposerLoop:
    """One event loop on one daemon thread, driving the agent's coroutines."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="faberon-proposer", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()


def _run_with_timeout[T](
    loop: _ProposerLoop, timeout: float, call: Callable[[], Awaitable[T]]
) -> T:
    """Run the call on the worker loop, returning its result within the bound.

    ``call`` is invoked on the loop and its awaitable awaited there. On
    timeout the in-flight call is cancelled and ``TimeoutError`` is raised.
    """
    # Propagate context to the worker thread
    ctx = contextvars.copy_context()

    async def run() -> T:
        return await ctx.run(call)

    future = asyncio.run_coroutine_threadsafe(run(), loop.loop)
    try:
        return future.result(timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise TimeoutError(f"proposer call exceeded {timeout} seconds") from None
