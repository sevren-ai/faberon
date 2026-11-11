/**
 * Reader for the shared Faberon config file (`faberon init` writes it).
 *
 * The clients only need the top-level scalars.
 * The `[env]` section is server-side only.
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** The config file path: `$FABERON_CONFIG` or the default location. */
export function configPath(env: NodeJS.ProcessEnv = process.env): string {
  return (
    env.FABERON_CONFIG ?? join(homedir(), ".config", "faberon", "config.toml")
  );
}

/** Top-level scalar entries from the config file; empty when absent. */
export function readConfigFile(path: string): Record<string, string> {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch {
    return {};
  }
  const values: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("[")) break;
    const match =
      /^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|(\d+))\s*(?:#.*)?$/.exec(
        trimmed,
      );
    const [, key, str, int] = match ?? [];
    const value = str ?? int;
    if (key !== undefined && value !== undefined) values[key] = value;
  }
  return values;
}
