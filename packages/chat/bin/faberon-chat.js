#!/usr/bin/env node
/**
 * `faberon-chat`: start the Pi chat interface (@earendil-works/pi-coding-agent)
 * without going through npx. This exists because `npx pi` can silently
 * resolve to the unrelated `pi` package on npm (it prints digits of pi) when
 * no local `pi` binary is installed. Forwards every argument unchanged.
 *
 * This file must stay plain CommonJS JavaScript: it is the package's "bin"
 * entry and runs before any build step exists.
 */
"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function fail(lines) {
  for (const line of lines) console.error(`faberon-chat: ${line}`);
  process.exit(1);
}

let piPkgDir;
try {
  const piPkgJson = require.resolve(
    "@earendil-works/pi-coding-agent/package.json",
    { paths: [__dirname] },
  );
  piPkgDir = path.dirname(piPkgJson);
} catch {
  fail([
    "the Pi CLI (@earendil-works/pi-coding-agent) is not installed next to this shim.",
    "Fix: cd packages/chat && npm ci --legacy-peer-deps",
  ]);
}

// Load the extension from this repo when invoked through a git checkout's
// npm bin shims (`npm --prefix packages/chat ...`). From an installed Pi
// package, Pi already loads the extension listed in package.json, so `-e`
// would load it twice.
const extension = path.resolve(__dirname, "..", "src", "index.ts");
const fromCheckout = fs.existsSync(
  path.resolve(__dirname, "..", "..", "..", "AGENTS.md"),
);
const passthrough = fromCheckout ? ["-e", extension] : [];

let entry;
try {
  const pkg = require(path.join(piPkgDir, "package.json"));
  const bin = typeof pkg.bin === "string" ? pkg.bin : pkg.bin && pkg.bin.pi;
  if (!bin) throw new Error("no bin.pi entry");
  entry = path.join(piPkgDir, bin);
} catch (err) {
  fail([`could not locate the Pi CLI entry point: ${err.message}`]);
}

const result = spawnSync(
  process.execPath,
  [entry, ...passthrough, ...process.argv.slice(2)],
  { stdio: "inherit" },
);

if (result.error) {
  fail([`failed to launch the Pi CLI: ${result.error.message}`]);
}
if (result.signal) {
  process.kill(process.pid, result.signal);
}
process.exit(result.status ?? 1);
