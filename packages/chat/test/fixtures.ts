import type {
  CampaignInfo,
  CampaignProgress,
  FaberonEvent,
  ResearchPlan,
} from "../src/api/types.js";

export function samplePlan(
  overrides: Partial<ResearchPlan> = {},
): ResearchPlan {
  return {
    goal: "Lower val_bpb on the baseline task",
    command: "python3 train.py",
    target_file: "train.py",
    metric: "val_bpb",
    baseline: 1.23,
    budget_gpu_hours: 10,
    max_experiments: 5,
    max_concurrency: 1,
    walltime: 30,
    stop_conditions: ["budget exhausted"],
    ...overrides,
  };
}

type MakeInfoOverrides = Omit<Partial<CampaignInfo>, "progress"> & {
  progress?: Partial<CampaignProgress>;
};

export function makeInfo(overrides: MakeInfoOverrides = {}): CampaignInfo {
  const { progress, ...rest } = overrides;
  return {
    campaign: {
      campaign_id: "abcdef12-0000-0000-0000-000000000000",
      workflow_id: "wf",
      plan: samplePlan(),
      repo_path: "/srv/autoresearch",
      branch: "main",
      start_sha: "e3f1c9a",
      poll_interval_seconds: 30,
      created_at: "2026-10-02T03:42:00",
      ...rest.campaign,
    },
    status: "active",
    progress: {
      experiments_done: 2,
      gpu_hours_burned: 0.05,
      baseline: 1.23,
      best_metric: 1.1,
      ...progress,
    },
    stop_reason: null,
    ...rest,
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
