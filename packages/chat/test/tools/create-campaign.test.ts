import { afterEach, describe, expect, it, vi } from "vitest";
import { Check } from "typebox/value";
import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "../../src/api/client.js";
import { samplePlan } from "../fixtures.js";
import {
  createCampaignTool,
  formatCreated,
  formatPlanForConfirm,
  planSchema,
} from "../../src/tools/create-campaign.js";
import type { ResearchPlan } from "../../src/api/types.js";

describe("formatCreated", () => {
  it("names the campaign and workflow ids", () => {
    const out = formatCreated({ campaign_id: "c", workflow_id: "w" });
    expect(out).toBe("campaign: c\nworkflow: w");
  });
});

describe("planSchema", () => {
  it("accepts a bare metric name", () => {
    expect(Check(planSchema, samplePlan())).toBe(true);
  });

  it("rejects a metric name that includes comments or spaces", () => {
    const plan = samplePlan({ metric: "val_bpb (lower = better)" });
    expect(Check(planSchema, plan)).toBe(false);
  });
});

describe("formatPlanForConfirm", () => {
  it("renders the full plan as JSON", () => {
    const plan = samplePlan();
    expect(JSON.parse(formatPlanForConfirm(plan))).toEqual(plan);
  });

  it("truncates long prose values but keeps the command in full", () => {
    const longText = "x".repeat(200);
    const shown = JSON.parse(
      formatPlanForConfirm(
        samplePlan({
          goal: longText,
          command: longText,
          stop_conditions: [longText],
        }),
      ),
    ) as ResearchPlan;
    const truncated = `${"x".repeat(120)}...`;
    expect(shown.goal).toBe(truncated);
    expect(shown.command).toBe(longText);
    expect(shown.stop_conditions).toEqual([truncated]);
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

  it("shows the full plan as JSON with the consequence in the dialog", async () => {
    mockCreate();
    const confirm = vi.fn().mockResolvedValue(true);
    await tool.execute("call", params, undefined, undefined, ctxWith(confirm));
    const [title, message] = confirm.mock.calls[0] as [string, string];
    expect(title).toMatch(/submit/i);
    expect(message).toContain("/srv/autoresearch");
    for (const field of [
      `"goal": "Lower val_bpb on the baseline task"`,
      `"command": "python3 train.py"`,
      `"target_file": "train.py"`,
      `"metric": "val_bpb"`,
      `"baseline": 1.23`,
      `"budget_gpu_hours": 10`,
      `"max_experiments": 5`,
      `"max_concurrency": 1`,
      `"gpus": 1`,
      `"walltime": 30`,
      `"budget exhausted"`,
    ]) {
      expect(message).toContain(field);
    }
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

  it("executes sequentially so its dialog cannot race another gated tool", () => {
    expect(tool.executionMode).toBe("sequential");
  });
});
