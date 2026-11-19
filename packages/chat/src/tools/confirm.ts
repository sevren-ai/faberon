/**
 * Shared confirmation gate for the write tools. When dialog UI is available,
 * the tool asks the human to confirm before calling the API. In
 * non-interactive modes the call goes through directly: invoking the tool
 * there is already an explicit act.
 *
 * Tools using this gate must declare `executionMode: "sequential"`. Pi runs
 * the tool calls of one turn concurrently by default, and the TUI shows only
 * one extension dialog at a time: a second confirm would silently replace
 * this one. Sequential execution keeps one dialog open at a time.
 */

import type { ExtensionToolContext } from "@earendil-works/pi-coding-agent";

/** Ask the human to confirm a write; true when the write may proceed. */
export async function confirmedByHuman(
  ctx: ExtensionToolContext,
  title: string,
  message: string,
): Promise<boolean> {
  return !ctx.hasUI || (await ctx.ui.confirm(title, message));
}
