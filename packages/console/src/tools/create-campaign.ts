/**
 * `faberon_create_campaign` tool: submit a new campaign from a research plan.
 */

import { randomUUID } from "node:crypto";
import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { FaberonClient } from "../api/client.js";
import type { CampaignCreated } from "../api/types.js";

/**
 * Render a created campaign for both the tool result and the slash command.
 */
export function formatCreated(created: CampaignCreated): string {
  return `campaign: ${created.campaign_id}\nworkflow: ${created.workflow_id}`;
}

const planSchema = Type.Object({
  goal: Type.String({
    description: "What the campaign tries to achieve.",
    minLength: 1,
  }),
  command: Type.String({
    description: "Training command each experiment runs.",
    minLength: 1,
  }),
  target_file: Type.String({
    description:
      "Path of the Python file the proposer edits, relative to the repo root, " +
      "e.g. 'train.py'.",
    minLength: 1,
  }),
  metric: Type.String({
    description:
      "Name of the metric under optimization, e.g. 'val_bpb'. The job log must " +
      "print a line naming it followed by a float, e.g. 'val_bpb: 1.10'.",
    minLength: 1,
  }),
  baseline: Type.Number({
    description: "Metric value of the starting commit.",
  }),
  budget_gpu_hours: Type.Number({
    description: "Total GPU-hour budget.",
    exclusiveMinimum: 0,
  }),
  max_experiments: Type.Integer({
    description: "Maximum number of experiments.",
    minimum: 1,
  }),
  max_concurrency: Type.Optional(
    Type.Integer({
      description: "Maximum parallel jobs.",
      default: 1,
      minimum: 1,
    }),
  ),
  walltime: Type.Integer({
    description: "Per-job walltime in minutes.",
    exclusiveMinimum: 0,
  }),
  stop_conditions: Type.Array(Type.String(), {
    description: "Conditions under which the campaign stops early.",
    minItems: 1,
  }),
});

export function createCampaignTool(client: FaberonClient) {
  return defineTool({
    name: "faberon_create_campaign",
    label: "Create a Faberon campaign",
    description:
      "Submit a new Faberon campaign from a research plan. The plan is " +
      "validated upon submission.",
    promptSnippet: "Submit a new Faberon campaign from a research plan",
    parameters: Type.Object({
      plan: planSchema,
      repo_path: Type.String({
        description: "Path to the target repo on the shared filesystem.",
        minLength: 1,
      }),
      poll_interval_seconds: Type.Optional(
        Type.Number({
          description: "Poll interval in seconds.",
          default: 30,
          exclusiveMinimum: 0,
        }),
      ),
    }),
    annotations: {},
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const created = await client.createCampaign({
        campaign_id: randomUUID(),
        plan: { max_concurrency: 1, ...params.plan },
        repo_path: params.repo_path,
        poll_interval_seconds: params.poll_interval_seconds ?? 30,
      });
      return {
        content: [{ type: "text", text: formatCreated(created) }],
        details: created,
      };
    },
  });
}
