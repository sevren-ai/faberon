/**
 * Thin typed HTTP client for the brain's v0 API.
 *
 * Reads the base URL and bearer token from the environment
 * (`FABERON_API_URL`, `FABERON_API_TOKEN`), matching the Faberon CLI.
 */

import type { ApiErrorBody, CampaignInfo } from "./types.js";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

export interface ClientConfig {
  baseUrl: string;
  token: string;
}

/** Resolve the client config from the environment. */
export function configFromEnv(env: NodeJS.ProcessEnv = process.env): ClientConfig {
  const token = env.FABERON_API_TOKEN;
  if (!token) {
    throw new Error(
      "FABERON_API_TOKEN is not set. The console talks to the brain " +
        "over an authenticated API; set the same token the brain uses.",
    );
  }
  const baseUrl = (env.FABERON_API_URL ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
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

  static fromEnv(env: NodeJS.ProcessEnv = process.env): FaberonClient {
    return new FaberonClient(configFromEnv(env));
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
        `Cannot reach the brain at ${this.config.baseUrl}: ${cause}. ` +
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
}
