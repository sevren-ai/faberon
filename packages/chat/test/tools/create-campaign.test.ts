import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "../../src/api/client.js";
import { samplePlan } from "../fixtures.js";
import {
  createCampaignTool,
  formatCreated,
} from "../../src/tools/create-campaign.js";

describe("formatCreated", () => {
  it("names the campaign and workflow ids", () => {
    const out = formatCreated({ campaign_id: "c", workflow_id: "w" });
    expect(out).toBe("campaign: c\nworkflow: w");
  });
});

describe("createCampaignTool", () => {
  const client = new FaberonClient({
    baseUrl: "http://localhost:9",
    token: "t",
  });
  const tool = createCampaignTool(client);
  const params = { plan: samplePlan(), repo_path: "/srv/autoresearch" };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockCreate() {
    return vi
      .spyOn(FaberonClient.prototype, "createCampaign")
      .mockResolvedValue({ campaign_id: "c", workflow_id: "w" });
  }

  function ctxWith(confirm: unknown, hasUI = true): ExtensionToolContext {
    return { hasUI, ui: { confirm } } as unknown as ExtensionToolContext;
  }

  it("submits after the human confirms in the UI", async () => {
    const created = mockCreate();
    const confirm = vi.fn().mockResolvedValue(true);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(confirm).toHaveBeenCalledOnce();
    expect(created).toHaveBeenCalledOnce();
    expect(result.isError).toBeUndefined();
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: "campaign: c\nworkflow: w",
    });
  });

  it("summarizes the plan & consequence in the dialog", async () => {
    mockCreate();
    const confirm = vi.fn().mockResolvedValue(true);
    await tool.execute("call", params, undefined, undefined, ctxWith(confirm));
    const [title, message] = confirm.mock.calls[0] as [string, string];
    expect(title).toMatch(/submit/i);
    expect(message).toContain("Lower val_bpb on the baseline task");
    expect(message).toContain("/srv/autoresearch");
    expect(message).toContain("python3 train.py");
    expect(message).toContain("10 GPU-hours, at most 5 experiments");
    expect(message).toContain("train.py");
    expect(message).toMatch(
      /until the budget is spent or a stop condition is met/i,
    );
  });

  it("does not submit when the human declines", async () => {
    const created = mockCreate();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(created).not.toHaveBeenCalled();
    expect(result.isError).toBe(true);
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: expect.stringMatching(/declined/i),
    });
  });

  it("submits without a dialog when no UI is available", async () => {
    const created = mockCreate();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm, false),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(created).toHaveBeenCalledOnce();
    expect(result.isError).toBeUndefined();
  });
});
