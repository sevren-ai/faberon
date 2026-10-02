import { describe, expect, it } from "vitest";
import { formatCampaigns } from "../src/tools/list-campaigns.js";
import type { CampaignInfo } from "../src/api/types.js";

function makeInfo(overrides: Partial<CampaignInfo> = {}): CampaignInfo {
  return {
    campaign: {
      campaign_id: "abcdef12-0000-0000-0000-000000000000",
      workflow_id: "wf",
      plan: {
        goal: "Lower val_bpb",
        command: "python train.py",
        metric_name: "val_bpb",
        metric_command: "python eval.py",
        baseline: 1.23,
        budget_gpu_hours: 10,
        max_experiments: 5,
        max_concurrency: 1,
        walltime: 30,
        stop_conditions: ["budget exhausted"],
      },
      repo_path: "/srv/autoresearch",
      poll_interval_seconds: 30,
      created_at: "2026-10-02T03:42:00",
    },
    status: "active",
    stop_reason: null,
    ...overrides,
  };
}

describe("formatCampaigns", () => {
  it("renders an empty list", () => {
    expect(formatCampaigns([])).toBe("No campaigns yet.");
  });

  it("renders a header plus one row per campaign", () => {
    const out = formatCampaigns([makeInfo(), makeInfo({ status: "ended" })]);
    const lines = out.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatch(/^ID\s+CREATED\s+STATUS\s+METRIC\s+REPO$/);
    const row = lines[1] ?? "";
    expect(row).toContain("abcdef12-0000-0000-0000-000000000000");
    expect(row).toContain("2026-10-02 03:42");
    expect(row).toContain("active");
    expect(row).toContain("val_bpb");
    expect(row).toContain("/srv/autoresearch");
    expect(lines[2]).toContain("ended");
  });
});
