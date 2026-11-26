/**
 * `faberon_create_successor` tool: start a successor campaign from a finished
 * campaign's best kept commit.
 */

import { randomUUID } from "node:crypto";
import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import { confirmedByHuman } from "./confirm.js";
import { formatCreated } from "./create-campaign.js";

export function createSuccessorTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_create_successor",
    label: "Create a successor campaign",
    description:
      "Start a successor campaign from a finished Faberon campaign's best " +
      "kept commit. The successor keeps the predecessor's research plan " +
      "under a fresh budget and experiment limit, with the baseline " +
      "reseeded from the predecessor's best kept metric. If the research " +
      "plan should change, create a new campaign with " +
      "faberon_create_campaign instead.",
    promptSnippet:
      "Start a successor from a finished Faberon campaign's best kept commit",
    parameters: Type.Object({
      campaign_id: Type.String({
        description: "UUID of the finished campaign to succeed.",
      }),
      budget_gpu_hours: Type.Number({
        description: "Fresh total GPU-hour budget for the successor.",
        exclusiveMinimum: 0,
      }),
      max_experiments: Type.Integer({
        description: "Fresh maximum number of experiments for the successor.",
        minimum: 1,
      }),
      branch: Type.Optional(
        Type.String({
          description:
            "Working branch for the successor. Defaults to a fresh " +
            "faberon/<short-id> branch created at the succession commit.",
          minLength: 1,
        }),
      ),
    }),
    annotations: {},
    executionMode: "sequential",
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const info = await client.getCampaign(params.campaign_id);
      const confirmed = await confirmedByHuman(
        ctx,
        "Start a successor campaign?",
        [
          `Predecessor: ${params.campaign_id} (${info.status})`,
          `budget_gpu_hours: ${params.budget_gpu_hours}`,
          `max_experiments: ${params.max_experiments}`,
          ...(params.branch !== undefined ? [`branch: ${params.branch}`] : []),
          "",
          "Faberon starts a new campaign from the predecessor's best kept commit and runs experiments until the fresh budget is spent or a stop condition is met.",
        ].join("\n"),
      );
      if (!confirmed) {
        return {
          content: [
            {
              type: "text",
              text: "The human declined the succession. No successor campaign was created. Do not create it unless they ask.",
            },
          ],
          details: undefined,
          isError: true,
        };
      }
      const created = await client.createSuccessor(params.campaign_id, {
        campaign_id: randomUUID(),
        budget_gpu_hours: params.budget_gpu_hours,
        max_experiments: params.max_experiments,
        ...(params.branch !== undefined ? { branch: params.branch } : {}),
      });
      return {
        content: [{ type: "text", text: formatCreated(created) }],
        details: created,
      };
    },
  });
}
