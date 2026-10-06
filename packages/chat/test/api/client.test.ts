import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  configFromEnv,
  FaberonClient,
} from "../../src/api/client.js";
import { makeEvent, makeInfo, samplePlan } from "../fixtures.js";

const sampleInfo = makeInfo();

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

  function lastCall(): [string, RequestInit] {
    return fetchMock.mock.calls[0] as [string, RequestInit];
  }

  it("sends the bearer token and parses the response", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([sampleInfo]), { status: 200 }),
    );
    const infos = await client().listCampaigns();
    expect(infos).toEqual([sampleInfo]);
    const [url, init] = lastCall();
    expect(url).toBe("http://x/v0/campaigns");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
  });

  it("raises ApiError with the FastAPI detail message", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "campaign not found" }), {
        status: 404,
      }),
    );
    const err = await client()
      .getCampaign("nope")
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("campaign not found");
  });

  it("raises a helpful error when Faberon is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("fetch failed: ECONNREFUSED"));
    await expect(client().listCampaigns()).rejects.toThrow(
      /Cannot reach Faberon/,
    );
  });

  it("posts a new campaign", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ campaign_id: "c", workflow_id: "w" }), {
        status: 201,
      }),
    );
    const created = await client().createCampaign({
      campaign_id: "c",
      plan: samplePlan(),
      repo_path: "/srv/autoresearch",
      poll_interval_seconds: 30,
    });
    expect(created).toEqual({ campaign_id: "c", workflow_id: "w" });
    const [url, init] = lastCall();
    expect(url).toBe("http://x/v0/campaigns");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body.campaign_id).toBe("c");
    expect(body.repo_path).toBe("/srv/autoresearch");
  });

  it("posts a cancellation with the reason", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ campaign_id: "c", status: "cancel requested" }),
        { status: 202 },
      ),
    );
    const result = await client().cancelCampaign("c", "no longer relevant");
    expect(result.status).toBe("cancel requested");
    const [url, init] = lastCall();
    expect(url).toBe("http://x/v0/campaigns/c/cancel");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      reason: "no longer relevant",
    });
  });

  it("posts an idea with text and reason", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ campaign_id: "c", status: "idea injected" }),
        { status: 202 },
      ),
    );
    const result = await client().injectIdea("c", "try a wider model", "hunch");
    expect(result.status).toBe("idea injected");
    const [url, init] = lastCall();
    expect(url).toBe("http://x/v0/campaigns/c/ideas");
    expect(JSON.parse(init.body as string)).toEqual({
      text: "try a wider model",
      reason: "hunch",
    });
  });

  it("posts a resume with an empty body", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ campaign_id: "c", status: "resume requested" }),
        { status: 202 },
      ),
    );
    const result = await client().resumeCampaign("c");
    expect(result.status).toBe("resume requested");
    const [url, init] = lastCall();
    expect(url).toBe("http://x/v0/campaigns/c/resume");
    expect(init.method).toBe("POST");
  });

  it("parses the events.jsonl snapshot", async () => {
    const events = [makeEvent(), makeEvent({ seq: 2 })];
    const body = events.map((e) => JSON.stringify(e)).join("\n") + "\n";
    fetchMock.mockResolvedValue(new Response(body, { status: 200 }));
    const parsed = await client().getEvents("c", 5);
    expect(parsed).toEqual(events);
    const [url] = lastCall();
    expect(url).toBe("http://x/v0/campaigns/c/events.jsonl?after=5");
  });

  it("raises ApiError on a failed events read", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "campaign not found" }), {
        status: 404,
      }),
    );
    const err = await client()
      .getEvents("nope")
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
  });
});
