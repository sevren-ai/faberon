import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "../../src/api/client.js";
import { cancelCampaignTool } from "../../src/tools/cancel-campaign.js";

describe("cancelCampaignTool", () => {
  const client = new FaberonClient({
    baseUrl: "http://localhost:9",
    token: "t",
  });
  const tool = cancelCampaignTool(client);
  const params = {
    campaign_id: "abcdef12-0000-0000-0000-000000000000",
    reason: "direction no longer useful",
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockCancel() {
    return vi
      .spyOn(FaberonClient.prototype, "cancelCampaign")
      .mockResolvedValue({
        campaign_id: params.campaign_id,
        status: "cancel requested",
      });
  }

  function ctxWith(confirm: unknown, hasUI = true): ExtensionToolContext {
    return { hasUI, ui: { confirm } } as unknown as ExtensionToolContext;
  }

  it("cancels after the human confirms in the UI", async () => {
    const cancelled = mockCancel();
    const confirm = vi.fn().mockResolvedValue(true);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(confirm).toHaveBeenCalledOnce();
    expect(cancelled).toHaveBeenCalledWith(params.campaign_id, params.reason);
    expect(result.isError).toBeUndefined();
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: "cancel requested",
    });
  });

  it("names the campaign, the reason, and the consequence in the dialog", async () => {
    mockCancel();
    const confirm = vi.fn().mockResolvedValue(true);
    await tool.execute("call", params, undefined, undefined, ctxWith(confirm));
    const [title, message] = confirm.mock.calls[0] as [string, string];
    expect(title).toMatch(/cancel/i);
    expect(message).toContain(params.campaign_id);
    expect(message).toContain(params.reason);
    expect(message).toMatch(/cannot be resumed/i);
  });

  it("does not cancel when the human declines", async () => {
    const cancelled = mockCancel();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(cancelled).not.toHaveBeenCalled();
    expect(result.isError).toBe(true);
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: expect.stringMatching(/declined/i),
    });
  });

  it("cancels without a dialog when no UI is available", async () => {
    const cancelled = mockCancel();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm, false),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(cancelled).toHaveBeenCalledOnce();
    expect(result.isError).toBeUndefined();
  });

  it("executes sequentially so its dialog cannot race another gated tool", () => {
    expect(tool.executionMode).toBe("sequential");
  });
});
