// Tests of extension.js without VS Code: a fake `vscode` module records what the
// extension registers. Run: node test/extension.test.js <python with hydra_etl>
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");

const PYTHON = process.argv[2];
if (!PYTHON) throw new Error("usage: node test/extension.test.js <python that can import hydra_etl.mcp>");

// ------------------------------------------------------------- fake vscode
const settings = {};          // "section.key" -> value
const shown = [];             // error messages
let folders = [];
let provider = null;
let providerId = null;
const emitters = [];

class EventEmitter {
  constructor() { this.listeners = []; this.event = (l) => this.listeners.push(l); emitters.push(this); }
  fire() { this.listeners.forEach((l) => l()); }
  dispose() {}
}
class McpStdioServerDefinition {
  constructor(label, command, args, env, version) {
    Object.assign(this, { label, command, args: args || [], env: env || {}, version });
  }
}
const vscode = {
  EventEmitter,
  McpStdioServerDefinition,
  Uri: { file: (p) => ({ fsPath: p, scheme: "file" }) },
  lm: { registerMcpServerDefinitionProvider: (id, p) => { providerId = id; provider = p; return { dispose() {} }; } },
  workspace: {
    get workspaceFolders() { return folders; },
    getConfiguration: (section) => ({ get: (k, d) => (`${section}.${k}` in settings ? settings[`${section}.${k}`] : d) }),
    onDidChangeWorkspaceFolders: () => ({ dispose() {} }),
    onDidChangeConfiguration: () => ({ dispose() {} }),
    createFileSystemWatcher: () => ({ onDidCreate() {}, dispose() {} }),
  },
  window: {
    createOutputChannel: () => ({ appendLine: (l) => process.env.VERBOSE && console.log("   log:", l), show() {}, dispose() {} }),
    showErrorMessage: async (m) => { shown.push(m); return undefined; },
    showInformationMessage: async () => undefined,
  },
  commands: { registerCommand: () => ({ dispose() {} }), executeCommand: async () => undefined },
  env: { clipboard: { writeText: async () => undefined } },
};
const load = Module._load;
Module._load = function (req, ...rest) { return req === "vscode" ? vscode : load.call(this, req, ...rest); };

const ext = require("../extension.js");
const pkg = require("../package.json");
const state = new Map();
const workspaceState = { get: (k) => state.get(k), update: async (k, v) => (v === undefined ? state.delete(k) : state.set(k, v)), keys: () => [...state.keys()] };
const context = { subscriptions: [], extension: { packageJSON: pkg }, workspaceState };

// ------------------------------------------------------------- folders
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hydra-vsext-"));
const project = path.join(tmp, "shop");
fs.mkdirSync(path.join(project, ".hydra"), { recursive: true });
fs.writeFileSync(path.join(project, ".hydra", "project.json"), "{}");
const other = path.join(tmp, "website");
fs.mkdirSync(other);
const folder = (dir) => ({ name: path.basename(dir), uri: vscode.Uri.file(dir) });

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test("package.json declares the provider the code registers", () => {
  ext.activate(context);
  assert.strictEqual(providerId, "hydraEtl.mcpServers");
  const ids = pkg.contributes.mcpServerDefinitionProviders.map((p) => p.id);
  assert.deepStrictEqual(ids, [providerId]);
  assert.ok(pkg.main === "./extension.js" && pkg.activationEvents.length > 0);
});

test("one server for a Hydra ETL folder, none for another folder", async () => {
  folders = [folder(project), folder(other)];
  const defs = await provider.provideMcpServerDefinitions();
  assert.strictEqual(defs.length, 1);
  assert.strictEqual(defs[0].label, "Hydra ETL (shop)");
  assert.strictEqual(defs[0].env.HYDRA_MCP_WORKSPACE, project);
  assert.strictEqual(defs[0].cwd.fsPath, project);
  assert.strictEqual(defs[0].version, pkg.version);
});

test("a folder with jobs/ only is a Hydra ETL folder too; the label is short with one folder", async () => {
  fs.mkdirSync(path.join(other, "jobs"));
  folders = [folder(other)];
  const defs = await provider.provideMcpServerDefinitions();
  assert.strictEqual(defs.length, 1);
  assert.strictEqual(defs[0].label, "Hydra ETL");
  fs.rmdirSync(path.join(other, "jobs"));
});

test("hydraEtl.mcp.enabled = false removes the server", async () => {
  folders = [folder(project)];
  settings["hydraEtl.mcp.enabled"] = false;
  assert.strictEqual((await provider.provideMcpServerDefinitions()).length, 0);
  delete settings["hydraEtl.mcp.enabled"];
});

test("no Python with Hydra ETL: the server does not start and the user is told how to install it", async () => {
  ext._test.found.clear();
  state.clear();
  settings["hydraEtl.mcp.python"] = path.join(tmp, "no-such-python");
  const savedPath = process.env.PATH;
  process.env.PATH = tmp; // nothing on the PATH either
  folders = [folder(project)];
  const [def] = await provider.provideMcpServerDefinitions();
  const res = await provider.resolveMcpServerDefinition(def);
  process.env.PATH = savedPath;
  assert.strictEqual(res, undefined);
  assert.ok(shown.some((m) => m.includes('pip install "hydra-etl[mcp]"')), shown.join("\n"));
});

test("hydraEtl.mcp.python is used when it can import Hydra ETL", async () => {
  ext._test.found.clear();
  settings["hydraEtl.mcp.python"] = PYTHON;
  const [def] = await provider.provideMcpServerDefinitions();
  const res = await provider.resolveMcpServerDefinition(def);
  assert.strictEqual(res.command, PYTHON);
  assert.deepStrictEqual(res.args, ["-m", "hydra_etl.mcp"]);
  delete settings["hydraEtl.mcp.python"];
});

test("the .venv of the folder comes before the PATH", () => {
  const bin = process.platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"];
  const venvPy = path.join(project, ".venv", ...bin);
  fs.mkdirSync(path.dirname(venvPy), { recursive: true });
  fs.writeFileSync(venvPy, "");
  const c = ext._test.candidates(project);
  assert.strictEqual(c[0].command, venvPy);
  assert.ok(c.findIndex((x) => x.from === "PATH") > 0);
});

test("the Python found is remembered for the next session, and checked again before use", async () => {
  assert.deepStrictEqual(state.get(`python:${project}`), { command: PYTHON, args: [] });
  ext._test.found.clear(); // a new session: the remembered one is tried first
  const [def] = await provider.provideMcpServerDefinitions();
  const t0 = Date.now();
  const res = await provider.resolveMcpServerDefinition(def);
  assert.strictEqual(res.command, PYTHON);
  assert.ok(Date.now() - t0 < 5000, `took ${Date.now() - t0} ms`);
});

test("the probe does not block: resolve returns a promise while Python runs", async () => {
  ext._test.found.clear();
  state.clear();
  settings["hydraEtl.mcp.python"] = PYTHON;
  const [def] = await provider.provideMcpServerDefinitions();
  let ticks = 0;
  const timer = setInterval(() => ticks++, 5);
  await provider.resolveMcpServerDefinition(def);
  clearInterval(timer);
  assert.ok(ticks > 0, "the event loop was blocked during the probe");
  delete settings["hydraEtl.mcp.python"];
});

test("the server the extension resolves starts and lists the Hydra ETL tools", async () => {
  ext._test.found.clear();
  settings["hydraEtl.mcp.python"] = PYTHON;
  const [def] = await provider.provideMcpServerDefinitions();
  const res = await provider.resolveMcpServerDefinition(def);
  const tools = await listTools(res);
  for (const t of ["hydra_write_job", "hydra_run_job", "hydra_check_job", "hydra_preview_data"]) {
    assert.ok(tools.includes(t), `${t} missing from ${tools.join(", ")}`);
  }
  delete settings["hydraEtl.mcp.python"];
});

// A minimal MCP client over stdio: initialize, then tools/list.
function listTools(def) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env, ...def.env };
    const p = require("child_process").spawn(def.command, def.args, { cwd: def.cwd.fsPath, env });
    let buf = "";
    let err = "";
    const send = (m) => p.stdin.write(JSON.stringify(m) + "\n");
    const timer = setTimeout(() => { p.kill(); reject(new Error("no answer in 60 s\n" + err)); }, 60000);
    p.stderr.on("data", (d) => (err += d));
    p.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        const msg = JSON.parse(line);
        if (msg.id === 1) {
          send({ jsonrpc: "2.0", method: "notifications/initialized" });
          send({ jsonrpc: "2.0", id: 2, method: "tools/list" });
        } else if (msg.id === 2) {
          clearTimeout(timer); p.kill();
          resolve(msg.result.tools.map((t) => t.name));
        }
      }
    });
    send({ jsonrpc: "2.0", id: 1, method: "initialize",
           params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "0" } } });
  });
}

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log(`ok    ${name}`); }
    catch (e) { failed++; console.log(`FAIL  ${name}\n      ${e.message.split("\n").join("\n      ")}`); }
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(failed ? `\n${failed} failed` : `\nall ${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
