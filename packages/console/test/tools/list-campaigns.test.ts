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
