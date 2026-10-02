/**
 * Faberon console: a Pi extension for drafting plans and steering campaigns.
 *
 * The extension exposes each v0 control-plane operation as a Pi tool (for the
 * model to call in conversation) plus a matching slash command (for the human
 * to invoke directly).
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { FaberonClient } from "./api/client.js";
import { formatCampaigns, listCampaignsTool } from "./tools/list-campaigns.js";

export default function faberonConsole(pi: ExtensionAPI): void {
  const client = FaberonClient.fromEnv();

  pi.registerTool(listCampaignsTool(client));

  pi.registerCommand("faberon-list", {
    description: "List Faberon campaigns with live status",
    handler: async (_args, ctx) => {
      try {
        const infos = await client.listCampaigns();
        ctx.ui.notify(formatCampaigns(infos), "info");
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        ctx.ui.notify(message, "error");
      }
    },
  });
}
