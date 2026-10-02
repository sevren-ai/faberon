import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, configFromEnv, FaberonClient } from "../src/api/client.js";
import type { CampaignInfo } from "../src/api/types.js";

const sampleInfo: CampaignInfo = {
  campaign: {
    campaign_id: "11111111-2222-3333-4444-555555555555",
    workflow_id: "11111111-2222-3333-4444-555555555555",
    plan: {
      goal: "Lower val_bpb on the baseline task",
      command: "python train.py",
      metric_name: "val_bpb",
      metric_command: "python eval.py",
      baseline: 1.23,
      budget_gpu_hours: 10,
      max_experiments: 5,
      max_concurrency: 1,
      walltime: 30,
      stop_conditions: ["budget exhausted"],
    },
    repo_path: "/home/user/autoresearch",
    poll_interval_seconds: 30,
    created_at: "2026-10-02T08:00:00",
  },
  status: "active",
  stop_reason: null,
};

describe("configFromEnv", () => {
  it("requires the token", () => {
    expect(() => configFromEnv({})).toThrow(/FABERON_API_TOKEN/);
  });

  it("defaults the base URL and strips trailing slashes", () => {
    const config = configFromEnv({
      FABERON_API_TOKEN: "tok",
      FABERON_API_URL: "http://localhost:9000/",
    });
    expect(config.baseUrl).toBe("http://localhost:9000");
    expect(config.token).toBe("tok");
  });

  it("uses the default URL when unset", () => {
    const config = configFromEnv({ FABERON_API_TOKEN: "tok" });
    expect(config.baseUrl).toBe("http://127.0.0.1:8000");
  });
});

describe("FaberonClient", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  function client(): FaberonClient {
    return new FaberonClient({ baseUrl: "http://x", token: "tok" });
  }

  it("sends the bearer token and parses the response", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([sampleInfo]), { status: 200 })
    );
    const infos = await client().listCampaigns();
    expect(infos).toEqual([sampleInfo]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://x/v0/campaigns");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok"
    );
  });

  it("raises ApiError with the FastAPI detail message", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "campaign not found" }), {
        status: 404,
      })
    );
    const err = await client()
      .getCampaign("nope")
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("campaign not found");
  });

  it("raises a helpful error when the brain is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("fetch failed: ECONNREFUSED"));
    await expect(client().listCampaigns()).rejects.toThrow(/Cannot reach the brain/);
  });
});
