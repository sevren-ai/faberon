import { describe, expect, it } from "vitest";
import { drafterPrompt } from "../src/drafter.js";
import { planSchema } from "../src/tools/create-campaign.js";

describe("drafterPrompt", () => {
  const prompt = drafterPrompt("/home/autoresearch");

  it("collects every required field", () => {
    // This test will fail if a new required field is added without updating the drafter
    for (const field of planSchema.required) {
      expect(prompt).toContain(field);
    }
  });

  it("defaults the repo path to the current working directory", () => {
    expect(prompt).toContain("repo_path");
    expect(prompt).toContain("Default: /home/autoresearch");
  });

  it("gates submission on human approval", () => {
    expect(prompt).toContain("faberon_create_campaign");
    expect(prompt).toMatch(/agree|approval/i);
    expect(prompt).toMatch(/never submit/i);
  });
});
