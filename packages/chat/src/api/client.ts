/**
 * Thin typed HTTP client for the v0 API.
 *
 * Reads the base URL and bearer token from the shared config file written
 * by `faberon init`.
 */

import { configPath, readConfigFile } from "./config.js";
import type {
  ApiErrorBody,
  CampaignCreate,
  CampaignCreated,
  CampaignInfo,
  FaberonEvent,
  StatusResponse,
} from "./types.js";

export interface ClientConfig {
  baseUrl: string;
  token: string;
}

/** Resolve the client config from the Faberon config file. */
export function loadClientConfig(
  env: NodeJS.ProcessEnv = process.env,
): ClientConfig {
  const file = readConfigFile(configPath(env));
  const token = file.api_token;
  if (!token) {
    throw new Error(
      `No API token in ${configPath(env)}. Faberon Chat talks to the API ` +
        "over an authenticated channel; run `faberon init` to set one up.",
    );
  }
  // api_url wins; otherwise derive from host and port, which the file must
  // carry (defaults exist only to write the file, never to read it).
  const derived =
    file.host !== undefined && file.port !== undefined
      ? `http://${file.host}:${file.port}`
      : undefined;
  const baseUrl = (file.api_url ?? derived)?.replace(/\/+$/, "");
  if (!baseUrl) {
    throw new Error(
      `No api_url (or host/port) in ${configPath(env)}: run \`faberon init\`.`,
    );
  }
  return { baseUrl, token };
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class FaberonClient {
  constructor(private readonly config: ClientConfig) {}

  static fromConfig(env: NodeJS.ProcessEnv = process.env): FaberonClient {
    return new FaberonClient(loadClientConfig(env));
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.config.baseUrl}${path}`;
    let res: Response;
    try {
      res = await fetch(url, {
        ...init,
        headers: {
          Authorization: `Bearer ${this.config.token}`,
          ...init?.headers,
        },
      });
    } catch (err) {
      const cause = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Cannot reach Faberon at ${this.config.baseUrl}: ${cause}. ` +
          "Is `faberon serve` running?",
      );
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as ApiErrorBody;
        if (body.detail) detail = body.detail;
      } catch {
        // Non-JSON error body; keep the status text.
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as T;
  }

  /** GET /v0/campaigns: all campaigns with live status, oldest first. */
  listCampaigns(): Promise<CampaignInfo[]> {
    return this.request<CampaignInfo[]>("/v0/campaigns");
  }

  /** GET /v0/campaigns/{id}: one campaign's record and live status. */
  getCampaign(campaignId: string): Promise<CampaignInfo> {
    return this.request<CampaignInfo>(`/v0/campaigns/${campaignId}`);
  }

  /** POST /v0/campaigns: submit a new campaign from a research plan. */
  createCampaign(body: CampaignCreate): Promise<CampaignCreated> {
    return this.request<CampaignCreated>("/v0/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /** POST /v0/campaigns/{id}/cancel: request cancellation of an active campaign. */
  cancelCampaign(campaignId: string, reason: string): Promise<StatusResponse> {
    return this.request<StatusResponse>(`/v0/campaigns/${campaignId}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
  }

  /** POST /v0/campaigns/{id}/ideas: inject an advisory idea into an active campaign. */
  injectIdea(
    campaignId: string,
    text: string,
    reason: string,
  ): Promise<StatusResponse> {
    return this.request<StatusResponse>(`/v0/campaigns/${campaignId}/ideas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, reason }),
    });
  }

  /** POST /v0/campaigns/{id}/resume: resume a pending campaign from its last checkpoint. */
  resumeCampaign(campaignId: string): Promise<StatusResponse> {
    return this.request<StatusResponse>(`/v0/campaigns/${campaignId}/resume`, {
      method: "POST",
    });
  }

  /** GET /v0/campaigns/{id}/events.jsonl: bounded snapshot of the campaign's ledger. */
  async getEvents(campaignId: string, after = 0): Promise<FaberonEvent[]> {
    const text = await this.requestText(
      `/v0/campaigns/${campaignId}/events.jsonl?after=${after}`,
    );
    return text
      .split("\n")
      .filter((line) => line.length > 0)
      .map((line) => JSON.parse(line) as FaberonEvent);
  }

  private async requestText(path: string, init?: RequestInit): Promise<string> {
    const url = `${this.config.baseUrl}${path}`;
    let res: Response;
    try {
      res = await fetch(url, {
        ...init,
        headers: {
          Authorization: `Bearer ${this.config.token}`,
          ...init?.headers,
        },
      });
    } catch (err) {
      const cause = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Cannot reach Faberon at ${this.config.baseUrl}: ${cause}. ` +
          "Is `faberon serve` running?",
      );
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as ApiErrorBody;
        if (body.detail) detail = body.detail;
      } catch {
        // Non-JSON error body; keep the status text.
      }
      throw new ApiError(res.status, detail);
    }
    return res.text();
  }
}
