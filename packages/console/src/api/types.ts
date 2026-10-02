/**
 * v0 API wire shapes, mirroring the Pydantic models. They are hand-maintained for now
 * but will be automatically generated later through an OpenAPI spec later.
 */

export interface ResearchPlan {
  goal: string;
  command: string;
  metric_name: string;
  metric_command: string;
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

/** FastAPI error body shape. */
export interface ApiErrorBody {
  detail?: string;
}
