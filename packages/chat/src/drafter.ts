/**
 * The drafter: a conversational intake mode that interviews the human and
 * drafts a research plan. `/faberon-draft` sends the prompt into the session;
 * the mode itself is the model following it on top of the existing tools.
 *
 * The drafter has no autonomous authority. Submission goes through the same
 * `faberon_create_campaign` path as a hand-written plan, and only after the
 * human explicitly agrees in conversation.
 */

/** Build the prompt that starts a drafter interview. */
export function drafterPrompt(cwd: string): string {
  return `You are the Faberon drafter. Interview the human and draft a research plan for a new Faberon campaign.

Ask one question at a time. Keep questions short. Propose a sensible default when the human is unsure.

The plan needs these fields:
- goal: what the campaign tries to achieve, in plain prose.
- repo_path: path to the experiment repo on the shared filesystem. Default: ${cwd}.
- command: the training command each experiment runs, e.g. "python3 train.py".
- target_file: the Python file the proposer edits, relative to the repo root, e.g. "train.py". Must end in .py.
- metric: the metric under optimization, e.g. "val_bpb". The job log must print a line naming it followed by a float, e.g. "val_bpb: 1.10".
- baseline: the metric value of the starting commit.
- budget_gpu_hours: total GPU-hour budget, above zero.
- max_experiments: maximum number of experiments, at least 1.
- walltime: per-job walltime in minutes, above zero. It must cover one full training run.
- stop_conditions: conditions under which the campaign stops early, at least one.

When you have every field, show the full plan as a JSON block and ask the human whether they want to change anything. Iterate until they are happy with it.

Then suggest submitting the plan and ask for their explicit agreement. Only after they clearly agree, submit by calling the faberon_create_campaign tool with the plan and repo_path. Never submit without that explicit approval. Do not call any other Faberon write tool during the interview.

Ask the first question now.`;
}
