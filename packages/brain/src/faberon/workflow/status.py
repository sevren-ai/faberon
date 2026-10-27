"""Derive a campaign's live status from the ledger and DBOS workflow state."""

from uuid import UUID

from dbos import DBOS, WorkflowStatusString
from dbos._utils import GlobalParams

from ..ledger import Ledger
from ..schema.campaign import Campaign, CampaignInfo, CampaignStatus
from ..schema.events import Actor, Event, EventType, StopReason

# DBOS workflow states in which the campaign will never write again. A
# a PENDING workflow may still be resumed, so it does not count as "dead".
_DEAD: set[str] = {
    WorkflowStatusString.ERROR.value,
    WorkflowStatusString.MAX_RECOVERY_ATTEMPTS_EXCEEDED.value,
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


def end_outdated_campaigns(ledger: Ledger) -> list[UUID]:
    """End active campaigns started before a Faberon upgrade. Return their ids.

    DBOS recovers workflows only when their application version (a hash of the
    workflow source) matches the running process. If DBOS can't recover an old
    workflow, it will remain stranded and blocking its target repo.
    """
    ended = []
    for campaign in ledger.list_campaigns():
        if get_campaign_info(ledger, campaign).status is not CampaignStatus.ACTIVE:
            continue
        info = DBOS.get_workflow_status(campaign.workflow_id)
        if info is not None and info.app_version == GlobalParams.app_version:
            continue
        if info is None:
            # If the workflow row is missing entirely, the DB got corrupt somehow.
            reason = "campaign ended: campaign record lost"
        else:
            DBOS.cancel_workflow(campaign.workflow_id)
            reason = "campaign ended: campaign got outdated by a Faberon upgrade"
        ledger.append(
            Event(
                campaign_id=campaign.campaign_id,
                actor=Actor.AGENT,
                type=EventType.CAMPAIGN_ENDED,
                reason=reason,
                payload={"stop_reason": StopReason.ERROR},
            )
        )
        ended.append(campaign.campaign_id)
    return ended
