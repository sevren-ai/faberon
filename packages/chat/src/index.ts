/**
 * Faberon Chat: a Pi extension for drafting plans and steering campaigns.
 *
 * The extension exposes each v0 control-plane operation as a Pi tool (for the
 * model to call in conversation) plus a matching slash command (for the human
 * to invoke directly). `faberon serve` stays CLI-only: it starts the server
 * the chat interface talks to.
 */

import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
} from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "./api/client.js";
import type { ResearchPlan } from "./api/types.js";
import { campaignEventsTool, formatEvents } from "./tools/campaign-events.js";
import { cancelCampaignTool } from "./tools/cancel-campaign.js";
import { createCampaignTool, formatCreated } from "./tools/create-campaign.js";
import { injectIdeaTool } from "./tools/inject-idea.js";
import { formatCampaigns, listCampaignsTool } from "./tools/list-campaigns.js";
import { resumeCampaignTool } from "./tools/resume-campaign.js";
import { formatCampaign, showCampaignTool } from "./tools/show-campaign.js";

/** Notify with the outcome of an operation the human invoked. */
async function notify(
  ctx: ExtensionCommandContext,
  operation: Promise<string>,
): Promise<void> {
  try {
    ctx.ui.notify(await operation, "info");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    ctx.ui.notify(message, "error");
  }
}

/** Prompt until the human enters a non-empty value. */
async function promptNonEmpty(
  ctx: ExtensionCommandContext,
  title: string,
  placeholder?: string,
): Promise<string | undefined> {
  for (;;) {
    const value = await ctx.ui.input(title, placeholder);
    if (value === undefined) {
      return undefined;
    }
    const trimmed = value.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
    ctx.ui.notify(`${title} must not be empty`, "warning");
  }
}

export default function faberonChat(pi: ExtensionAPI): void {
  const client = FaberonClient.fromEnv();

  pi.registerTool(listCampaignsTool(client));
  pi.registerTool(showCampaignTool(client));
  pi.registerTool(campaignEventsTool(client));
  pi.registerTool(createCampaignTool(client));
  pi.registerTool(cancelCampaignTool(client));
  pi.registerTool(injectIdeaTool(client));
  pi.registerTool(resumeCampaignTool(client));

  pi.registerCommand("faberon-list", {
    description: "List Faberon campaigns with live status",
    handler: async (_args, ctx) => {
      await notify(
        ctx,
        client.listCampaigns().then((infos) => formatCampaigns(infos)),
      );
    },
  });

  pi.registerCommand("faberon-show", {
    description: "Show one Faberon campaign's status and plan",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const campaignId =
        args.trim() || (await promptNonEmpty(ctx, "Campaign ID"));
      if (!campaignId) return;
      await notify(
        ctx,
        client.getCampaign(campaignId).then((info) => formatCampaign(info)),
      );
    },
  });

  pi.registerCommand("faberon-events", {
    description: "Print a Faberon campaign's ledger. --verbose adds payloads.",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const tokens = args.split(/\s+/).filter((t) => t.length > 0);
      const verbose = tokens.includes("--verbose") || tokens.includes("-v");
      const positional = tokens.filter((t) => !t.startsWith("-"));
      const campaignId =
        positional[0] ?? (await promptNonEmpty(ctx, "Campaign ID"));
      if (!campaignId) return;
      await notify(
        ctx,
        client
          .getEvents(campaignId)
          .then((events) => formatEvents(events, verbose)),
      );
    },
  });

  pi.registerCommand("faberon-create", {
    description:
      "Submit a new Faberon campaign: /faberon-create <plan.json> [repo-path]",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const tokens = args.split(/\s+/).filter((t) => t.length > 0);
      const planPath =
        tokens[0] ?? (await promptNonEmpty(ctx, "Plan JSON file"));
      if (!planPath) return;
      const repoPath = tokens[1] ?? ctx.cwd;
      await notify(ctx, createFromFile(ctx, client, planPath, repoPath));
    },
  });

  pi.registerCommand("faberon-cancel", {
    description: "Request cancellation of an active Faberon campaign",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const tokens = args.split(/\s+/).filter((t) => t.length > 0);
      const campaignId =
        tokens[0] ?? (await promptNonEmpty(ctx, "Campaign ID"));
      if (!campaignId) return;
      const reason =
        tokens.slice(1).join(" ").trim() ||
        (await promptNonEmpty(ctx, "Reason to cancel"));
      if (!reason) return;
      await notify(
        ctx,
        client.cancelCampaign(campaignId, reason).then((r) => r.status),
      );
    },
  });

  pi.registerCommand("faberon-idea", {
    description:
      "Inject an advisory idea into an active Faberon campaign: " +
      "/faberon-idea <campaign-id> <idea text>",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const tokens = args.split(/\s+/).filter((t) => t.length > 0);
      const campaignId =
        tokens[0] ?? (await promptNonEmpty(ctx, "Campaign ID"));
      if (!campaignId) return;
      const text =
        tokens.slice(1).join(" ").trim() || (await promptNonEmpty(ctx, "Idea"));
      if (!text) return;
      const reason = await promptNonEmpty(ctx, "Reason for the idea");
      if (!reason) return;
      await notify(
        ctx,
        client.injectIdea(campaignId, text, reason).then((r) => r.status),
      );
    },
  });

  pi.registerCommand("faberon-resume", {
    description: "Resume a pending Faberon campaign from its last checkpoint",
    getArgumentCompletions: () => null,
    handler: async (args, ctx) => {
      const campaignId =
        args.trim() || (await promptNonEmpty(ctx, "Campaign ID"));
      if (!campaignId) return;
      await notify(
        ctx,
        client.resumeCampaign(campaignId).then((r) => r.status),
      );
    },
  });
}

/** Read a plan JSON file and submit it through the create path. */
async function createFromFile(
  ctx: ExtensionCommandContext,
  client: FaberonClient,
  planPath: string,
  repoPath: string,
): Promise<string> {
  const raw = await readFile(resolve(ctx.cwd, planPath), "utf8");
  const plan = JSON.parse(raw) as ResearchPlan;
  const created = await client.createCampaign({
    campaign_id: randomUUID(),
    plan,
    repo_path: resolve(ctx.cwd, repoPath),
    poll_interval_seconds: 30,
  });
  return formatCreated(created);
}
