/**
 * `faberon_resume_campaign` tool: resume a pending campaign.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";

export function resumeCampaignTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_resume_campaign",
    label: "Resume a Faberon campaign",
    description:
      "Resume a pending Faberon campaign's workflow from its last " +
      "checkpoint, for example after Faberon was restarted with recovery " +
      "disabled.",
    promptSnippet: "Resume a pending Faberon campaign",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "Campaign UUID.",
      }),
    }),
    annotations: { idempotentHint: true },
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const result = await client.resumeCampaign(params.campaign_id);
      return {
        content: [{ type: "text", text: result.status }],
        details: result,
      };
    },
  });
}
