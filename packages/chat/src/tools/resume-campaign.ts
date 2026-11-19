/**
 * `faberon_resume_campaign` tool: resume a pending campaign.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import { confirmedByHuman } from "./confirm.js";

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
    executionMode: "sequential",
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const confirmed = await confirmedByHuman(
        ctx,
        "Resume this Faberon campaign?",
        [
          `Campaign: ${params.campaign_id}`,
          "",
          "The campaign continues running experiments and spending its remaining GPU-hour budget.",
        ].join("\n"),
      );
      if (!confirmed) {
        return {
          content: [
            {
              type: "text",
              text: "The human declined the resume. The campaign stays pending. Do not resume it unless they ask.",
            },
          ],
          details: undefined,
          isError: true,
        };
      }
      const result = await client.resumeCampaign(params.campaign_id);
      return {
        content: [{ type: "text", text: result.status }],
        details: result,
      };
    },
  });
}
