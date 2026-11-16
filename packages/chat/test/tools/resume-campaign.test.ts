import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "../../src/api/client.js";
import { resumeCampaignTool } from "../../src/tools/resume-campaign.js";

describe("resumeCampaignTool", () => {
  const client = new FaberonClient({
    baseUrl: "http://localhost:9",
    token: "t",
  });
  const tool = resumeCampaignTool(client);
  const params = { campaign_id: "abcdef12-0000-0000-0000-000000000000" };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockResume() {
    return vi
      .spyOn(FaberonClient.prototype, "resumeCampaign")
      .mockResolvedValue({
        campaign_id: params.campaign_id,
        status: "resume requested",
      });
  }

  function ctxWith(confirm: unknown, hasUI = true): ExtensionToolContext {
    return { hasUI, ui: { confirm } } as unknown as ExtensionToolContext;
  }

  it("resumes after the human confirms in the UI", async () => {
    const resumed = mockResume();
    const confirm = vi.fn().mockResolvedValue(true);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(confirm).toHaveBeenCalledOnce();
    expect(resumed).toHaveBeenCalledWith(params.campaign_id);
    expect(result.isError).toBeUndefined();
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: "resume requested",
    });
  });

  it("names the campaign and the consequence in the dialog", async () => {
    mockResume();
    const confirm = vi.fn().mockResolvedValue(true);
    await tool.execute("call", params, undefined, undefined, ctxWith(confirm));
    const [title, message] = confirm.mock.calls[0] as [string, string];
    expect(title).toMatch(/resume/i);
    expect(message).toContain(params.campaign_id);
    expect(message).toMatch(/spending its remaining GPU-hour budget/i);
  });

  it("does not resume when the human declines", async () => {
    const resumed = mockResume();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(resumed).not.toHaveBeenCalled();
    expect(result.isError).toBe(true);
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: expect.stringMatching(/declined/i),
    });
  });

  it("resumes without a dialog when no UI is available", async () => {
    const resumed = mockResume();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm, false),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(resumed).toHaveBeenCalledOnce();
    expect(result.isError).toBeUndefined();
  });
});
