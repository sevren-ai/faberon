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

  it("confirms the repo first, then guesses from it before asking", () => {
    expect(prompt).toMatch(/confirm the target repo/i);
    expect(prompt).toContain("Default: /home/autoresearch");
  });

  it("gates running the baseline on permission", () => {
    expect(prompt).toMatch(/never run it without asking/i);
    expect(prompt).toMatch(/how long the run will take/i);
  });

  it("gates submission on a separate yes after the plan is settled", () => {
    expect(prompt).toContain("faberon_create_campaign");
    // Plan approval alone must not trigger submission.
    expect(prompt).toMatch(/not consent to submit/i);
    expect(prompt).toMatch(/submit the plan now, yes or no/i);
    // The submit question comes with a plain-terms explanation of the consequence.
    expect(prompt).toMatch(/starts a campaign/i);
    // A "no" is defined: hold the plan, do not submit, offer to save it
    // into the target repo for hand editing and later submission.
    expect(prompt).toMatch(/if the answer is no, do not submit/i);
    expect(prompt).toContain(".faberon/plan.json");
    expect(prompt).toContain("/faberon-create");
  });

  it("closes the interview after submission with follow-up pointers", () => {
    expect(prompt).toMatch(/after a successful submission/i);
    expect(prompt).toContain("/faberon-show");
    expect(prompt).toContain("/faberon-events");
  });
});
