#!/usr/bin/env node

import { runCompileCommand } from "../lib/compile.js";

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const flags = new Map();

  for (let index = 0; index < rest.length; index += 1) {
    const arg = rest[index];
    if (!arg.startsWith("--")) {
      throw new Error(`Unexpected argument '${arg}'.`);
    }
    const value = rest[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Flag '${arg}' requires a value.`);
    }
    flags.set(arg, value);
    index += 1;
  }

  return { command, flags };
}

async function main() {
  const { command, flags } = parseArgs(process.argv.slice(2));

  if (command !== "compile") {
    throw new Error("Usage: agentir compile --config agentir.config.json");
  }

  const configPath = flags.get("--config");
  if (!configPath) {
    throw new Error("agentir compile requires --config <path>.");
  }

  const result = await runCompileCommand({
    configPath,
    cwd: process.cwd(),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
