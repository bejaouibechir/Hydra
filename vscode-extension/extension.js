// HYDRA ETL for VS Code: makes the Hydra ETL MCP server available to the agents of
// VS Code (GitHub Copilot agent mode and any extension that uses MCP tools).
//
// One server per workspace folder that looks like a Hydra ETL project (.hydra/,
// jobs/ or workflows/). The server only reads and writes inside that folder.
// The Python that runs it is found without any setting in the usual cases:
// hydraEtl.mcp.python, a .venv / venv of the folder, the interpreter chosen in
// the Python extension, then `py -3`, `python`, `python3` on the PATH. The first
// one that can import hydra_etl.mcp wins.
"use strict";

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const cp = require("child_process");

const PROVIDER_ID = "hydraEtl.mcpServers";
const IS_WIN = process.platform === "win32";
const INSTALL = 'pip install "hydra-etl[mcp]"';

let output;
let memory; // workspaceState: the Python found, kept from one session to the next
const found = new Map(); // folder -> { command, args } (or null: nothing works)

function log(msg) {
  if (output) output.appendLine(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

function isHydraFolder(dir) {
  return ["/.hydra", "/jobs", "/workflows"].some((p) => {
    try {
      return fs.statSync(dir + p).isDirectory();
    } catch {
      return false;
    }
  });
}

function venvPythons(dir) {
  const rel = IS_WIN ? ["Scripts", "python.exe"] : ["bin", "python"];
  return [".venv", "venv", "env"]
    .map((v) => path.join(dir, v, ...rel))
    .filter((p) => fs.existsSync(p));
}

/** The interpreters to try, best first: [{ command, args, from }]. */
function candidates(dir) {
  const cfg = vscode.workspace.getConfiguration("hydraEtl.mcp", vscode.Uri.file(dir));
  const out = [];
  const own = (cfg.get("python") || "").trim();
  if (own) out.push({ command: own, args: [], from: "hydraEtl.mcp.python" });
  for (const p of venvPythons(dir)) out.push({ command: p, args: [], from: "virtual environment of the folder" });
  const py = (vscode.workspace.getConfiguration("python", vscode.Uri.file(dir)).get("defaultInterpreterPath") || "").trim();
  if (py && py !== "python") {
    out.push({ command: py.replace("${workspaceFolder}", dir), args: [], from: "python.defaultInterpreterPath" });
  }
  if (IS_WIN) out.push({ command: "py", args: ["-3"], from: "PATH" });
  out.push({ command: "python", args: [], from: "PATH" });
  if (!IS_WIN) out.push({ command: "python3", args: [], from: "PATH" });
  return out;
}

// Finds hydra_etl/mcp and the MCP SDK without importing them: importing Hydra ETL
// loads pandas and takes seconds; this takes a few milliseconds after Python starts.
const PROBE =
  "import importlib.util as u, os, sys\n" +
  "h = u.find_spec('hydra_etl')\n" +
  "ok = bool(h and h.origin and os.path.isdir(os.path.join(os.path.dirname(h.origin), 'mcp')) and u.find_spec('mcp'))\n" +
  "print(sys.version_info >= (3, 10) and ok)";

/** True when this interpreter has Hydra ETL with its MCP server (asynchronous: VS Code is never blocked). */
function canRun(c) {
  return new Promise((resolve) => {
    cp.execFile(c.command, [...c.args, "-c", PROBE], { timeout: 15000, windowsHide: true }, (err, stdout) => {
      resolve(!err && String(stdout).trim() === "True");
    });
  });
}

async function findPython(dir) {
  if (found.has(dir)) return found.get(dir);
  const remembered = memory && memory.get(`python:${dir}`);
  const list = candidates(dir);
  if (remembered) list.unshift({ ...remembered, from: "remembered from the last session" });
  for (const c of list) {
    if (await canRun(c)) {
      log(`${dir}: Hydra ETL found with ${[c.command, ...c.args].join(" ")} (${c.from})`);
      found.set(dir, c);
      if (memory) memory.update(`python:${dir}`, { command: c.command, args: c.args });
      return c;
    }
    log(`${dir}: ${[c.command, ...c.args].join(" ")} (${c.from}) has no Hydra ETL with its MCP server`);
  }
  found.set(dir, null);
  return null;
}

function folders() {
  return (vscode.workspace.workspaceFolders || [])
    .filter((f) => f.uri.scheme === "file")
    .map((f) => ({ name: f.name, dir: f.uri.fsPath }))
    .filter((f) => vscode.workspace.getConfiguration("hydraEtl.mcp", vscode.Uri.file(f.dir)).get("enabled", true))
    .filter((f) => isHydraFolder(f.dir));
}

function definitionFor(f, version) {
  const several = (vscode.workspace.workspaceFolders || []).length > 1;
  const label = several ? `Hydra ETL (${f.name})` : "Hydra ETL";
  // command and args are filled in resolveMcpServerDefinition, when the server starts
  const def = new vscode.McpStdioServerDefinition(label, "python", ["-m", "hydra_etl.mcp"],
    { HYDRA_MCP_WORKSPACE: f.dir, PYTHONIOENCODING: "utf-8" }, version);
  def.cwd = vscode.Uri.file(f.dir);
  return def;
}

function activate(context) {
  output = vscode.window.createOutputChannel("Hydra ETL");
  memory = context.workspaceState;
  context.subscriptions.push(output);
  const version = (context.extension && context.extension.packageJSON.version) || "0";

  if (!vscode.lm || typeof vscode.lm.registerMcpServerDefinitionProvider !== "function") {
    log("This version of VS Code has no MCP API: the Hydra ETL MCP server is not registered (VS Code 1.101 or later).");
    return;
  }

  const changed = new vscode.EventEmitter();
  context.subscriptions.push(changed);

  const provider = {
    onDidChangeMcpServerDefinitions: changed.event,

    provideMcpServerDefinitions: async () => {
      const list = folders();
      log(`MCP servers offered: ${list.map((f) => f.dir).join(", ") || "none (no Hydra ETL folder open)"}`);
      return list.map((f) => definitionFor(f, version));
    },

    resolveMcpServerDefinition: async (def) => {
      const dir = def.env && def.env.HYDRA_MCP_WORKSPACE;
      if (!dir) return def;
      const py = await findPython(String(dir));
      if (!py) {
        const pick = await vscode.window.showErrorMessage(
          `Hydra ETL: no Python with Hydra ETL found for ${path.basename(String(dir))}. ` +
            `Install it with: ${INSTALL} (Python 3.10 or later), or set hydraEtl.mcp.python.`,
          "Copy the install command",
          "Open settings",
        );
        if (pick === "Copy the install command") await vscode.env.clipboard.writeText(INSTALL);
        if (pick === "Open settings") await vscode.commands.executeCommand("workbench.action.openSettings", "hydraEtl.mcp");
        return undefined; // the server does not start
      }
      def.command = py.command;
      def.args = [...py.args, "-m", "hydra_etl.mcp"];
      return def;
    },
  };

  context.subscriptions.push(vscode.lm.registerMcpServerDefinitionProvider(PROVIDER_ID, provider));

  const refresh = () => {
    found.clear();
    changed.fire();
  };
  const forget = () => {
    for (const k of (memory.keys ? memory.keys() : [])) if (k.startsWith("python:")) memory.update(k, undefined);
    refresh();
  };
  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(refresh),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("hydraEtl.mcp") || e.affectsConfiguration("python.defaultInterpreterPath")) forget();
    }),
    vscode.commands.registerCommand("hydraEtl.mcp.refresh", () => {
      forget();
      vscode.window.showInformationMessage("Hydra ETL: MCP server list refreshed.");
    }),
    vscode.commands.registerCommand("hydraEtl.mcp.showLog", () => output.show()),
  );
  // a .hydra/ or jobs/ folder created later (hdrctl init, Studio) makes the folder eligible
  const watcher = vscode.workspace.createFileSystemWatcher("**/{.hydra,jobs,workflows}", false, true, true);
  watcher.onDidCreate(refresh);
  context.subscriptions.push(watcher);
  log(`Hydra ETL ${version}: MCP server provider registered.`);
}

function deactivate() {}

module.exports = { activate, deactivate, _test: { candidates, isHydraFolder, findPython, found } };
