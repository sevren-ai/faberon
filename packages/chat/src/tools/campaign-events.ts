/**
 * `faberon_campaign_events` tool: read a campaign's ledger.
 */

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import type { FaberonEvent } from "../api/types.js";

/**
 * Render one event as a human-readable line
 */
export function formatEvent(event: FaberonEvent, verbose = false): string {
  const ts = event.ts.slice(0, 19).replace("T", " ") + "Z";
  let line = `${ts} ${event.actor.padEnd(5)} ${event.type.padEnd(28)} ${event.reason}`;
  if (verbose && Object.keys(event.payload).length > 0) {
    line += `\n${" ".repeat(20)} ${JSON.stringify(event.payload)}`;
  }
  return line;
}

/**
 * Render a bounded ledger read for both the tool result and the slash command.
 */
export function formatEvents(events: FaberonEvent[], verbose = false): string {
  if (events.length === 0) {
    return "No events yet.";
  }
  return events.map((event) => formatEvent(event, verbose)).join("\n");
}

export function campaignEventsTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_campaign_events",
    label: "Read a Faberon campaign's ledger",
    description:
      "Read the event ledger of one Faberon campaign: proposals, " +
      "completions, judgments, budget burn. Pass `after` with the last seen " +
      "sequence number to page in only newer events.",
    promptSnippet: "Read a Faberon campaign's event ledger",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "Campaign UUID.",
      }),
      after: Type.Optional(
        Type.Integer({
          description: "Only events after this ledger sequence number.",
          default: 0,
          minimum: 0,
        }),
      ),
      verbose: Type.Optional(
        Type.Boolean({
          description: "Include event payloads.",
          default: false,
        }),
      ),
    }),
    annotations: { readOnlyHint: true },
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const events = await client.getEvents(
        params.campaign_id,
        params.after ?? 0,
      );
      return {
        content: [{ type: "text", text: formatEvents(events, params.verbose) }],
        details: { events },
      };
    },
  });
}
