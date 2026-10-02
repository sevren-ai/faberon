/**
 * `faberon_list_campaigns` tool: list campaigns with live status.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import type { CampaignInfo } from "../api/types.js";

/**
 * Render campaign rows for both the tool result and the slash command.
 */
export function formatCampaigns(infos: CampaignInfo[]): string {
  if (infos.length === 0) {
    return "No campaigns yet.";
  }
  const pad = (s: string, n: number) => s.padEnd(n, " ");
  const header = `${pad("ID", 36)}  ${pad("CREATED", 16)}  ${pad("STATUS", 6)}  ${pad("METRIC", 12)}  REPO`;
  const lines = infos.map((info) => {
    const c = info.campaign;
    const created = c.created_at.slice(0, 16).replace("T", " ");
    return `${c.campaign_id}  ${created}  ${pad(info.status, 6)}  ${pad(c.plan.metric_name, 12)}  ${c.repo_path}`;
  });
  return [header, ...lines].join("\n");
}

export function listCampaignsTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_list_campaigns",
    label: "List Faberon campaigns",
    description:
      "List all Faberon research campaigns with their live status (active, " +
      "ended, died), creation time, repo path, and metric. Oldest first.",
    promptSnippet: "List Faberon campaigns and their live status",
    parameters: Type.Object({}),
    annotations: { readOnlyHint: true },
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      const infos = await client.listCampaigns();
      return {
        content: [{ type: "text", text: formatCampaigns(infos) }],
        details: { campaigns: infos },
      };
    },
  });
}
