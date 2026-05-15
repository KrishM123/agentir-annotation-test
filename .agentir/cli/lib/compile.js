import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const DEFAULT_ALLOCATOR_BASE_URL = "http://127.0.0.1:8080";
const PACKAGE_DIR = path.dirname(fileURLToPath(import.meta.url));

function commandFailureMessage(error, fallback) {
  if (error && typeof error === "object") {
    const stderr =
      "stderr" in error && typeof error.stderr === "string"
        ? error.stderr.trim()
        : "";
    if (stderr) {
      return stderr;
    }
    const stdout =
      "stdout" in error && typeof error.stdout === "string"
        ? error.stdout.trim()
        : "";
    if (stdout) {
      return stdout;
    }
  }
  return fallback;
}

function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, "");
}

function parseContractPath(contractPath) {
  const [rawPath, rawSymbol = ""] = contractPath.split("#", 2);
  const modulePath = rawPath.trim();
  const symbol = rawSymbol.trim();
  if (!modulePath) {
    throw new Error("agentir.config.json contractPath must include a file path.");
  }
  return { modulePath, symbol };
}

async function loadConfig(configPath) {
  const resolved = path.resolve(configPath);
  const parsed = JSON.parse(await readFile(resolved, "utf8"));
  if (!parsed || typeof parsed !== "object") {
    throw new Error("agentir config must be a JSON object.");
  }
  return {
    resolvedPath: resolved,
    config: parsed,
  };
}

function resolveCompileInputs(config) {
  const workflowIdFromEnv = process.env.AGENTIR_WORKFLOW_ID?.trim() ?? "";
  const workflowKeyFromEnv = process.env.AGENTIR_WORKFLOW_KEY?.trim() ?? "";
  const workflowId = workflowIdFromEnv || String(config.workflowId ?? "").trim();
  const allocatorBaseUrl = normalizeBaseUrl(
    (process.env.AGENTIR_BASE_URL?.trim() ?? "") ||
      String(config.allocatorBaseUrl ?? "").trim() ||
      DEFAULT_ALLOCATOR_BASE_URL,
  );
  const workflowKey = workflowKeyFromEnv;

  if (!workflowId) {
    throw new Error("Missing workflow id. Set AGENTIR_WORKFLOW_ID or workflowId in agentir.config.json.");
  }
  if (!workflowKey) {
    throw new Error("Missing AGENTIR_WORKFLOW_KEY.");
  }

  const contractPath = String(config.contractPath ?? "").trim();
  if (!contractPath) {
    throw new Error(
      "agentir.config.json must include contractPath for the current AgentIR compile workflow.",
    );
  }

  return {
    workflowId,
    workflowIdSource: workflowIdFromEnv ? "env" : "config",
    allocatorBaseUrl,
    workflowKey,
    contractPath,
  };
}

async function loadAiSdkContract(repoRoot, resolvedContractPath, symbol) {
  const helperPath = path.join(PACKAGE_DIR, "load-ai-sdk-contract.mjs");
  const tsxImport = await import.meta.resolve("tsx/esm");
  let stdout;
  try {
    ({ stdout } = await execFileAsync(
      process.execPath,
      ["--import", tsxImport, helperPath, repoRoot, resolvedContractPath, symbol],
      { cwd: repoRoot },
    ));
  } catch (error) {
    throw new Error(
      commandFailureMessage(error, "AI SDK contract emission failed."),
    );
  }
  return JSON.parse(stdout);
}

async function loadLangGraphContract(repoRoot, resolvedContractPath, symbol) {
  const helperPath = path.join(PACKAGE_DIR, "load-langgraph-contract.py");
  let stdout;
  try {
    ({ stdout } = await execFileAsync(
      "python3",
      [helperPath, repoRoot, resolvedContractPath, symbol],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          AGENTIR_CONTRACT_EMIT: process.env.AGENTIR_CONTRACT_EMIT ?? "1",
        },
      },
    ));
  } catch (error) {
    throw new Error(
      commandFailureMessage(error, "LangGraph contract emission failed."),
    );
  }
  return JSON.parse(stdout);
}

async function loadContract(repoRoot, configDir, contractPath) {
  const { modulePath, symbol } = parseContractPath(contractPath);
  const resolvedContractPath = path.resolve(configDir, modulePath);
  const extension = path.extname(resolvedContractPath).toLowerCase();

  if (extension === ".json") {
    return JSON.parse(await readFile(resolvedContractPath, "utf8"));
  }
  if (extension === ".py") {
    if (!symbol) {
      throw new Error("Python contractPath values must include a '#symbol' suffix.");
    }
    return loadLangGraphContract(repoRoot, resolvedContractPath, symbol);
  }
  if ([".js", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"].includes(extension)) {
    if (!symbol) {
      throw new Error("JavaScript and TypeScript contractPath values must include a '#symbol' suffix.");
    }
    return loadAiSdkContract(repoRoot, resolvedContractPath, symbol);
  }

  throw new Error(
    `Unsupported contractPath '${contractPath}'. Use a .json, .py, .js, or .ts module path with '#symbol'.`,
  );
}

async function postCompileRequest(input) {
  const response = await fetch(`${input.allocatorBaseUrl}/blackbox/compile`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "api-key": input.workflowKey,
    },
    body: JSON.stringify({
      workflow_id: input.workflowId,
      contract: input.contract,
    }),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const errorText =
      payload &&
      typeof payload === "object" &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : `Compile failed with status ${response.status}.`;
    throw new Error(errorText);
  }

  return payload;
}

function countGraph(payload) {
  const graph =
    payload?.graph ??
    payload?.compiled_workflow ??
    payload?.workflow?.graph ??
    null;

  const nodes = Array.isArray(graph?.nodes) ? graph.nodes.length : null;
  const edges = Array.isArray(graph?.edges) ? graph.edges.length : null;
  return { nodes, edges };
}

export async function runCompileCommand(input) {
  const { resolvedPath, config } = await loadConfig(path.resolve(input.cwd, input.configPath));
  const compileInput = resolveCompileInputs(config);
  const configDir = path.dirname(resolvedPath);
  const contract = await loadContract(input.cwd, configDir, compileInput.contractPath);
  const payload = await postCompileRequest({
    allocatorBaseUrl: compileInput.allocatorBaseUrl,
    workflowId: compileInput.workflowId,
    workflowKey: compileInput.workflowKey,
    contract,
  });
  const counts = countGraph(payload);

  return {
    status: payload?.status ?? "ok",
    workflow_id: compileInput.workflowId,
    workflow_id_source: compileInput.workflowIdSource,
    allocator_base_url: compileInput.allocatorBaseUrl,
    contract_path: compileInput.contractPath,
    node_count: counts.nodes,
    edge_count: counts.edges,
  };
}
