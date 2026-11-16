/**
 * Shared confirmation gate for the write tools. When dialog UI is available,
 * the tool asks the human to confirm before calling the API. In
 * non-interactive modes the call goes through directly: invoking the tool
 * there is already an explicit act.
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
