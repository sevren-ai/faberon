/**
 * `faberon_show_campaign` tool: show one campaign's status and plan.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import type { CampaignInfo } from "../api/types.js";

/**
 * Render one campaign for both the tool result and the slash command.
 */
export function formatCampaign(info: CampaignInfo): string {
  const campaign = info.campaign;
  const created = campaign.created_at.slice(0, 16).replace("T", " ");
  const lines = [
    `campaign: ${campaign.campaign_id}`,
    `created:  ${created}`,
    `repo:     ${campaign.repo_path}`,
    `goal:     ${campaign.plan.goal}`,
    `metric:   ${campaign.plan.metric_name}`,
    `budget:   ${campaign.plan.budget_gpu_hours} gpu-hours`,
    `max exp:  ${campaign.plan.max_experiments}`,
    `status:   ${info.status}`,
  ];
  if (info.stop_reason != null) {
    lines.push(`reason:   ${info.stop_reason}`);
  }
  return lines.join("\n");
}

export function showCampaignTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_show_campaign",
    label: "Show one Faberon campaign",
    description:
      "Show one Faberon campaign's live status and research plan: goal, " +
      "metric, budget, experiment limit, and stop reason when it has ended.",
    promptSnippet: "Show one Faberon campaign's status and plan",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "Campaign UUID.",
      }),
    }),
    annotations: { readOnlyHint: true },
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const info = await client.getCampaign(params.campaign_id);
      return {
        content: [{ type: "text", text: formatCampaign(info) }],
        details: { campaign: info },
      };
    },
  });
}
