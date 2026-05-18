"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const tl = require("azure-pipelines-task-lib/task");
const { loginAzureRM } = require("azure-pipelines-tasks-azure-arm-rest/azCliUtility");

const DEFAULT_API_VERSION = "2025-03-01-preview";
const DEFAULT_TIMEOUT_SECONDS = "600";
const VENV_NAME = "microbots-log-analyzer-venv";
const VENV_READY_MARKER = ".microbots-venv-ready-v1";

function runCommand(command, args, env) {
  const result = spawnSync(command, args, { stdio: "inherit", env: env || process.env });
  if (result.error) throw new Error(`Failed to run ${command}: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} -> exit ${result.status}`);
}

function input(name, required) {
  const value = tl.getInput(name, required);
  return value ? value.trim() : value;
}

function resolveLogPath(codebasePath, logFilePath) {
  return path.isAbsolute(logFilePath)
    ? path.resolve(logFilePath)
    : path.resolve(codebasePath, logFilePath);
}

function getInputs() {
  const inputs = {
    serviceConnection: input("serviceConnection", true),
    deploymentName: input("deploymentName", true),
    endpoint: input("endpoint", true),
    apiVersion: input("apiVersion", false) || DEFAULT_API_VERSION,
    codebasePath: tl.getPathInput("codebasePath", true, true),
    logFilePath: input("logFilePath", true),
    timeoutSeconds: input("timeoutSeconds", false) || DEFAULT_TIMEOUT_SECONDS,
  };

  validateInputs(inputs);
  return inputs;
}

function validateInputs(inputs) {
  if (!fs.existsSync(inputs.codebasePath)) {
    throw new Error(`codebasePath does not exist: ${inputs.codebasePath}`);
  }

  if (!fs.statSync(inputs.codebasePath).isDirectory()) {
    throw new Error(`codebasePath must be a directory: ${inputs.codebasePath}`);
  }

  const logPath = resolveLogPath(inputs.codebasePath, inputs.logFilePath);
  if (!fs.existsSync(logPath) || !fs.statSync(logPath).isFile()) {
    throw new Error(`logFilePath does not exist: ${logPath}`);
  }
  inputs.logFilePath = logPath;

  try {
    const endpoint = new URL(inputs.endpoint);
    if (endpoint.protocol !== "https:" && endpoint.protocol !== "http:") throw new Error();
  } catch (_) {
    throw new Error(`endpoint must be a valid HTTP or HTTPS URL: ${inputs.endpoint}`);
  }

  const timeoutSeconds = Number(inputs.timeoutSeconds);
  if (!Number.isSafeInteger(timeoutSeconds) || timeoutSeconds <= 0) {
    throw new Error(`timeoutSeconds must be a positive integer: ${inputs.timeoutSeconds}`);
  }
  inputs.timeoutSeconds = String(timeoutSeconds);
}

async function loginWithServiceConnection(serviceConnection) {
  console.log("##[section]MicrobotsLogAnalyzer: authenticating with Azure service connection");
  const previousAzureOutput = process.env.AZURE_CORE_OUTPUT;
  const originalLoc = tl.loc;

  process.env.AZURE_CORE_OUTPUT = "none";
  tl.loc = function loc(key, ...args) {
    if (key === "LoginFailed" || key === "ErrorInSettingUpSubscription") return key;
    return originalLoc(key, ...args);
  };

  try {
    await loginAzureRM(serviceConnection);
  } catch (error) {
    throw new Error(`Azure service connection login failed for '${serviceConnection}': ${error.message || String(error)}`);
  } finally {
    tl.loc = originalLoc;
    if (previousAzureOutput === undefined) delete process.env.AZURE_CORE_OUTPUT;
    else process.env.AZURE_CORE_OUTPUT = previousAzureOutput;
  }

  console.log("##[section]MicrobotsLogAnalyzer: Azure authentication complete");
}

function venvPythonPath(venvDir) {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function setupVenv() {
  const venvRoot = process.env.AGENT_TEMPDIRECTORY
    || process.env.PIPELINE_WORKSPACE
    || process.env.RUNNER_TEMP
    || "/tmp";
  const venvDir = path.join(venvRoot, VENV_NAME);
  const python = venvPythonPath(venvDir);
  const venvReadyFile = path.join(venvDir, VENV_READY_MARKER);

  if (fs.existsSync(python) && fs.existsSync(venvReadyFile)) {
    console.log(`##[section]MicrobotsLogAnalyzer: reusing Python environment at ${venvDir}`);
    return python;
  }

  if (fs.existsSync(venvDir)) fs.rmSync(venvDir, { recursive: true, force: true });

  console.log(`##[section]MicrobotsLogAnalyzer: creating Python environment at ${venvDir}`);
  runCommand("python3", ["-m", "venv", venvDir]);
  console.log("Installing Python dependencies (microbots, Azure identity)...");
  runCommand(python, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"]);
  runCommand(python, ["-m", "pip", "install", "--quiet", "microbots[azure_ad]"]);
  fs.writeFileSync(venvReadyFile, new Date().toISOString());

  return python;
}

function microbotsEnvironment(inputs) {
  return Object.assign({}, process.env, {
    OPEN_AI_DEPLOYMENT_NAME: inputs.deploymentName,
    OPEN_AI_END_POINT: inputs.endpoint,
    OPEN_AI_API_VERSION: inputs.apiVersion,
    AZURE_OPENAI_ENDPOINT: inputs.endpoint,
    AZURE_OPENAI_API_VERSION: inputs.apiVersion,
  });
}

function runLogAnalyzer(python, inputs) {
  const scriptPath = path.join(__dirname, "log_analyzer_runner.py");
  runCommand(
    python,
    [scriptPath, inputs.codebasePath, inputs.logFilePath, inputs.timeoutSeconds],
    microbotsEnvironment(inputs)
  );
}

async function run() {
  try {
    const inputs = getInputs();
    await loginWithServiceConnection(inputs.serviceConnection);
    const python = setupVenv();
    runLogAnalyzer(python, inputs);
    tl.setResult(tl.TaskResult.Succeeded, "LogAnalysisBot completed");
  } catch (error) {
    tl.setResult(tl.TaskResult.Failed, error.message || String(error));
  } finally {
    try { spawnSync("az", ["account", "clear"], { stdio: "ignore" }); } catch (_) {}
  }
}

run();
