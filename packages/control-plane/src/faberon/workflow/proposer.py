"""Pydantic AI proposer for single-file experiments."""

import os
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model, infer_model

from ..schema.events import Event
from ..schema.plan import ResearchPlan
from .models import Proposal


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

    _prompt = ("Propose one focused ML experiment. Read the target file and the "
               "campaign history before deciding. Return the complete replacement "
               "file and a concise rationale. The replacement must differ from the "
               "current file.")

    def __init__(self, events: CampaignEventReader, model: Model) -> None:
        self._events = events
        self._model = model
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
        def validate_changed_content(
            ctx: RunContext[ProposalContext], proposal: Proposal
        ) -> Proposal:
            if proposal.content == ctx.deps.current_content:
                raise ModelRetry("The replacement must change the target file.")
            return proposal

    @classmethod
    def from_env(cls, events: CampaignEventReader) -> AgentProposer:
        """Build a proposer from ``FABERON_MODEL``, resolved at startup."""
        name = os.environ.get("FABERON_MODEL", "").strip()
        if not name:
            raise RuntimeError("FABERON_MODEL is not set")
        return cls(events, infer_model(name))

    def propose(
        self,
        campaign_id: UUID,
        plan: ResearchPlan,
        current_content: str,
    ) -> Proposal:
        """Propose one replacement using the plan and current campaign state."""
        prompt = (
            f"Goal: {plan.goal}\n"
            f"Metric: {plan.metric_name} (lower is better)\n"
            "Current train.py:\n"
            "<target_file>\n"
            f"{current_content}\n"
            "</target_file>"
        )
        result = self._agent.run_sync(
            prompt,
            model=self._model,
            deps=ProposalContext(
                events=self._events,
                campaign_id=campaign_id,
                current_content=current_content,
            ),
        )
        return result.output
