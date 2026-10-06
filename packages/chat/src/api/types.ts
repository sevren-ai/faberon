/**
 * v0 API wire shapes, mirroring the Pydantic models. They are hand-maintained for now
 * but will be automatically generated later through an OpenAPI spec later.
 */

export interface ResearchPlan {
  goal: string;
  command: string;
  target_file: string;
  metric: string;
  baseline: number;
  budget_gpu_hours: number;
  max_experiments: number;
  max_concurrency: number;
  walltime: number;
  stop_conditions: string[];
}

export type CampaignStatus = "active" | "ended" | "died";

export interface Campaign {
  campaign_id: string;
  workflow_id: string;
  plan: ResearchPlan;
  repo_path: string;
  poll_interval_seconds: number;
  created_at: string;
}

export interface CampaignInfo {
  campaign: Campaign;
  status: CampaignStatus;
  stop_reason?: string | null;
}

/** POST /v0/campaigns body. */
export interface CampaignCreate {
  campaign_id: string;
  plan: ResearchPlan;
  repo_path: string;
  poll_interval_seconds: number;
}

/** POST /v0/campaigns result: new campaign ID and DBOS workflow ID. */
export interface CampaignCreated {
  campaign_id: string;
  workflow_id: string;
}

/** Status body returned by the write endpoints. */
export interface StatusResponse {
  campaign_id: string;
  status: string;
}

/** Ledger event record, one line of the campaign's event log. */
export interface FaberonEvent {
  seq: number | null;
  ts: string;
  campaign_id: string;
  actor: "agent" | "human";
  type: string;
  reason: string;
  payload: Record<string, unknown>;
}

/** FastAPI error body shape. */
export interface ApiErrorBody {
  detail?: string;
}
