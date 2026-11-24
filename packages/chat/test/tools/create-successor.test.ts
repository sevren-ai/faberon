import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "../../src/api/client.js";
import { createSuccessorTool } from "../../src/tools/create-successor.js";
import { makeInfo } from "../fixtures.js";

describe("createSuccessorTool", () => {
  const client = new FaberonClient({
    baseUrl: "http://localhost:9",
    token: "t",
  });
  const tool = createSuccessorTool(client);
  const params = {
    campaign_id: "abcdef12-0000-0000-0000-000000000000",
    budget_gpu_hours: 5,
    max_experiments: 2,
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockGetCampaign() {
    return vi
      .spyOn(FaberonClient.prototype, "getCampaign")
      .mockResolvedValue(makeInfo({ status: "ended" }));
  }

  function mockCreate() {
    return vi
      .spyOn(FaberonClient.prototype, "createSuccessor")
      .mockResolvedValue({ campaign_id: "new-id", workflow_id: "new-id" });
  }

  function ctxWith(confirm: unknown, hasUI = true): ExtensionToolContext {
    return { hasUI, ui: { confirm } } as unknown as ExtensionToolContext;
  }

  it("creates the successor after the human confirms in the UI", async () => {
    mockGetCampaign();
    const create = mockCreate();
    const confirm = vi.fn().mockResolvedValue(true);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(confirm).toHaveBeenCalledOnce();
    expect(create).toHaveBeenCalledWith(params.campaign_id, {
      campaign_id: expect.any(String),
      budget_gpu_hours: 5,
      max_experiments: 2,
    });
    expect(result.isError).toBeUndefined();
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: expect.stringContaining("new-id"),
    });
  });

  it("names the predecessor, its best kept metric, and the fresh limits", async () => {
    mockGetCampaign();
    mockCreate();
    const confirm = vi.fn().mockResolvedValue(true);
    await tool.execute("call", params, undefined, undefined, ctxWith(confirm));
    const [title, message] = confirm.mock.calls[0] as [string, string];
    expect(title).toMatch(/successor/i);
    expect(message).toContain(params.campaign_id);
    expect(message).toContain("ended");
    expect(message).toContain("1.1");
    expect(message).toContain("5 GPU-hours");
    expect(message).toContain("2 experiments");
  });

  it("does not create when the human declines", async () => {
    mockGetCampaign();
    const create = mockCreate();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm),
    );
    expect(create).not.toHaveBeenCalled();
    expect(result.isError).toBe(true);
    expect(result.content[0]).toMatchObject({
      type: "text",
      text: expect.stringMatching(/declined/i),
    });
  });

  it("creates without a dialog when no UI is available", async () => {
    mockGetCampaign();
    const create = mockCreate();
    const confirm = vi.fn().mockResolvedValue(false);
    const result = await tool.execute(
      "call",
      params,
      undefined,
      undefined,
      ctxWith(confirm, false),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledOnce();
    expect(result.isError).toBeUndefined();
  });

  it("executes sequentially so its dialog cannot race another gated tool", () => {
    expect(tool.executionMode).toBe("sequential");
  });

  it("refers to create when the research plan should change", () => {
    expect(tool.description).toContain("faberon_create_campaign");
  });
});
