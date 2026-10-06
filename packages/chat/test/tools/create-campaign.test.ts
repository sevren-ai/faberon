import { describe, expect, it } from "vitest";
import { formatCreated } from "../../src/tools/create-campaign.js";

describe("formatCreated", () => {
  it("names the campaign and workflow ids", () => {
    const out = formatCreated({ campaign_id: "c", workflow_id: "w" });
    expect(out).toBe("campaign: c\nworkflow: w");
  });
});
