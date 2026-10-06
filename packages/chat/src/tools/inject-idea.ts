/**
 * `faberon_inject_idea` tool: inject an advisory idea into an active campaign.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";

export function injectIdeaTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_inject_idea",
    label: "Inject an idea into a Faberon campaign",
    description:
      "Inject a human idea into an active Faberon campaign. The idea lands " +
      "in the ledger as idea.injected and the proposer weighs it at its next " +
      "decision boundary. Advisory only: nothing forces execution.",
    promptSnippet: "Inject an advisory idea into an active Faberon campaign",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "Campaign UUID.",
      }),
      text: Type.String({
        description: "The idea itself, read by the proposer.",
        minLength: 1,
      }),
      reason: Type.String({
        description: "Why the idea is injected. Recorded in the ledger.",
        minLength: 1,
      }),
    }),
    annotations: { idempotentHint: false },
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const result = await client.injectIdea(
        params.campaign_id,
        params.text,
        params.reason,
      );
      return {
        content: [{ type: "text", text: result.status }],
        details: result,
      };
    },
  });
}
