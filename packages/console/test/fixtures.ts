import type {
  CampaignInfo,
  FaberonEvent,
  ResearchPlan,
} from "../src/api/types.js";

export function samplePlan(
  overrides: Partial<ResearchPlan> = {},
): ResearchPlan {
  return {
    goal: "Lower val_bpb on the baseline task",
    command: "python train.py",
    metric_name: "val_bpb",
    baseline: 1.23,
    budget_gpu_hours: 10,
    max_experiments: 5,
    max_concurrency: 1,
    walltime: 30,
    stop_conditions: ["budget exhausted"],
    ...overrides,
  };
}

export function makeInfo(overrides: Partial<CampaignInfo> = {}): CampaignInfo {
  return {
    campaign: {
      campaign_id: "abcdef12-0000-0000-0000-000000000000",
      workflow_id: "wf",
      plan: samplePlan(),
      repo_path: "/srv/autoresearch",
      poll_interval_seconds: 30,
      created_at: "2026-10-02T03:42:00",
      ...overrides.campaign,
    },
    status: "active",
    stop_reason: null,
    ...overrides,
  };
}

export function makeEvent(overrides: Partial<FaberonEvent> = {}): FaberonEvent {
  return {
    seq: 1,
    ts: "2026-10-02T03:42:00Z",
    campaign_id: "abcdef12-0000-0000-0000-000000000000",
    actor: "agent",
    type: "campaign.created",
    reason: "plan accepted",
    payload: {},
    ...overrides,
  };
}
