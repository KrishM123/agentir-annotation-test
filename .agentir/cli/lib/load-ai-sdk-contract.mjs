import path from "node:path";
import { pathToFileURL } from "node:url";

import { buildContract, contractToJson } from "@agentir-annotators/ai-sdk";

const [, , repoRoot, resolvedContractPath, symbol] = process.argv;
if (!repoRoot || !resolvedContractPath || !symbol) {
  throw new Error(
    "Usage: load-ai-sdk-contract.mjs <repo-root> <module-path> <symbol>",
  );
}

const imported = await import(pathToFileURL(resolvedContractPath).href);
const value = imported[symbol];
if (!value) {
  throw new Error(
    `Module '${path.relative(repoRoot, resolvedContractPath)}' does not export '${symbol}'.`,
  );
}

if (value && typeof value === "object" && "entry" in value && "nodes" in value && "edges" in value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
  process.exit(0);
}

const contract = buildContract(value);
process.stdout.write(`${JSON.stringify(contractToJson(contract))}\n`);
