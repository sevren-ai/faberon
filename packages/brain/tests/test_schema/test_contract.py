"""Guard against changing a string and accidentally breaking bwd-compat.

These enum values are persisted in Postgres ledger rows, so renames must
be deliberate as they can break existing campaigns.
When adding a new value, the dict here needs to be extended as well.
If a rename ever is deliberate, it needs an 'UPDATE events SET type = ...'
migration shipped with the release.
"""

from faberon.schema import Actor, CampaignStatus, EventType, StopReason


def test_event_type_vocabulary():
    """The persisted EventType strings match the contract exactly."""
    assert {t.name: t.value for t in EventType} == {
        "CAMPAIGN_CREATED": "campaign.created",
        "CAMPAIGN_ENDED": "campaign.ended",
        "CAMPAIGN_CRASHED": "campaign.crashed",
        "CANCEL_REQUESTED": "campaign.cancel_requested",
        "IDEA_INJECTED": "idea.injected",
        "EXPERIMENT_DESIGNING": "experiment.designing",
        "EXPERIMENT_PROPOSED": "experiment.proposed",
        "EXPERIMENT_PROPOSE_FAILED": "experiment.propose_failed",
        "EXPERIMENT_SUBMITTED": "experiment.submitted",
        "EXPERIMENT_COMPLETED": "experiment.completed",
        "EXPERIMENT_JUDGED": "experiment.judged",
    }


def test_actor_vocabulary():
    """The persisted Actor strings match the contract exactly."""
    assert {a.name: a.value for a in Actor} == {
        "AGENT": "agent",
        "HUMAN": "human",
    }


def test_stop_reason_vocabulary():
    """The persisted StopReason strings match the contract exactly."""
    assert {r.name: r.value for r in StopReason} == {
        "CANCELLED": "cancelled",
        "BUDGET_EXHAUSTED": "budget_exhausted",
        "MAX_EXPERIMENTS": "max_experiments",
        "ERROR": "error",
    }


def test_campaign_status_vocabulary():
    """The persisted CampaignStatus strings match the contract exactly."""
    assert {s.name: s.value for s in CampaignStatus} == {
        "ACTIVE": "active",
        "ENDED": "ended",
        "DIED": "died",
    }
