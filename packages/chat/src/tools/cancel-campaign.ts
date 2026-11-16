/**
 * `faberon_cancel_campaign` tool: request cancellation of an active campaign.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import { confirmedByHuman } from "./confirm.js";

export function cancelCampaignTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_cancel_campaign",
    label: "Cancel a Faberon campaign",
    description:
      "Request cancellation of an active Faberon campaign. " +
      "Requires a human-given reason.",
    promptSnippet: "Cancel an active Faberon campaign",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "Campaign UUID.",
      }),
      reason: Type.String({
        description: "Why the campaign is cancelled. Recorded in the ledger.",
        minLength: 1,
      }),
    }),
    annotations: { destructiveHint: true, idempotentHint: true },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const confirmed = await confirmedByHuman(
        ctx,
        "Cancel this Faberon campaign?",
        [
          `Campaign: ${params.campaign_id}`,
          `Reason: ${params.reason}`,
          "",
          "The campaign ends early and cannot be resumed.",
        ].join("\n"),
      );
      if (!confirmed) {
        return {
          content: [
            {
              type: "text",
              text: "The human declined the cancellation. The campaign keeps running. Do not cancel it unless they ask.",
            },
          ],
          details: undefined,
          isError: true,
        };
      }
      const result = await client.cancelCampaign(
        params.campaign_id,
        params.reason,
      );
      return {
        content: [{ type: "text", text: result.status }],
        details: result,
      };
    },
  });
}
