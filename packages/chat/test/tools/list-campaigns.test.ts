import { describe, expect, it } from "vitest";
import { formatCampaigns } from "../../src/tools/list-campaigns.js";
import { makeInfo } from "../fixtures.js";

describe("formatCampaigns", () => {
  it("renders an empty list", () => {
    expect(formatCampaigns([])).toBe("No campaigns yet.");
  });

  it("renders a header plus one row per campaign", () => {
    const out = formatCampaigns([makeInfo(), makeInfo({ status: "ended" })]);
    const lines = out.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatch(
      /^ID\s+CREATED\s+STATUS\s+METRIC\s+EXPS\s+GPU-H\s+BEST\s+REPO$/,
    );
    const row = lines[1] ?? "";
    expect(row).toContain("abcdef12-0000-0000-0000-000000000000");
    expect(row).toContain("2026-10-02 03:42");
    expect(row).toContain("active");
    expect(row).toContain("val_bpb");
    expect(row).toContain("2/5");
    expect(row).toContain("0.05/10");
    expect(row).toContain("1.23->1.1");
    expect(row).toContain("/srv/autoresearch");
    expect(lines[2]).toContain("ended");
  });

  it("marks the baseline as best when no experiment has been kept", () => {
    const out = formatCampaigns([
      makeInfo({ progress: { best_metric: null } }),
    ]);
    const row = out.split("\n")[1] ?? "";
    expect(row).toContain("baseline:1.23");
    expect(row).not.toContain("1.23->");
  });
});
