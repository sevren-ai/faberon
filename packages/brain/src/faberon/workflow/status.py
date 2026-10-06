"""Derive a campaign's live status from the ledger and DBOS workflow state."""

from dbos import DBOS, WorkflowStatusString

from ..ledger import Ledger
from ..schema.campaign import Campaign, CampaignInfo, CampaignStatus
from ..schema.events import EventType

# DBOS workflow states in which the campaign will never write again. A
# PENDING workflow may still be resumed, so it does count as "dead".
_DEAD = {
    WorkflowStatusString.ERROR,
    WorkflowStatusString.MAX_RECOVERY_ATTEMPTS_EXCEEDED,
}


def get_campaign_info(ledger: Ledger, campaign: Campaign) -> CampaignInfo:
    """Return one campaign with its live status attached."""
    # If we find a campaign.ended event, we know it has ended
    ended = next(
        (
            e
            for e in ledger.campaign_events(campaign.campaign_id)
            if e.type == EventType.CAMPAIGN_ENDED
        ),
        None,
    )
    if ended is not None:
        return CampaignInfo(
            campaign=campaign,
            status=CampaignStatus.ENDED,
            stop_reason=str(ended.payload["stop_reason"]),
        )
    # otherwise, we rely on status from DBOS
    info = DBOS.get_workflow_status(campaign.workflow_id)
    if info is not None and info.status in _DEAD:
        return CampaignInfo(campaign=campaign, status=CampaignStatus.DIED)
    return CampaignInfo(campaign=campaign, status=CampaignStatus.ACTIVE)
