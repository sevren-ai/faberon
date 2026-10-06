import { describe, expect, it } from "vitest";
import { makeInfo } from "../fixtures.js";
import { formatCampaign } from "../../src/tools/show-campaign.js";

describe("formatCampaign", () => {
  it("renders the plan and live status", () => {
    const out = formatCampaign(makeInfo());
    expect(out).toContain("campaign: abcdef12-0000-0000-0000-000000000000");
    expect(out).toContain("created:  2026-10-02 03:42");
    expect(out).toContain("repo:     /srv/autoresearch");
    expect(out).toContain("goal:     Lower val_bpb on the baseline task");
    expect(out).toContain("metric:   val_bpb");
    expect(out).toContain("budget:   10 gpu-hours");
    expect(out).toContain("max exp:  5");
    expect(out).toContain("status:   active");
    expect(out).not.toContain("reason:");
  });

  it("names the stop reason of an ended campaign", () => {
    const out = formatCampaign(
      makeInfo({ status: "ended", stop_reason: "budget_exhausted" }),
    );
    expect(out).toContain("status:   ended");
    expect(out).toContain("reason:   budget_exhausted");
  });
});
