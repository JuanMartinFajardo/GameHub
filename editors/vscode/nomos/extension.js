// SPDX-License-Identifier: Apache-2.0
// Extensión de VS Code para Nomos (.game): diagnósticos con `gamehub check --format json` al abrir
// y al guardar, y formato con `gamehub fmt --stdin`. No necesita compilación (JavaScript plano).

"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const path = require("path");

/** Cómo ejecutar gamehub: el ajuste `nomos.command` (por defecto, ["gamehub"]). */
function command() {
  const configured = vscode.workspace.getConfiguration("nomos").get("command");
  return Array.isArray(configured) && configured.length > 0 ? configured : ["gamehub"];
}

/** Directorio desde el que ejecutar gamehub: la carpeta del espacio de trabajo del archivo. */
function workingDirectory(uri) {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  return folder ? folder.uri.fsPath : path.dirname(uri.fsPath);
}

/** Ejecuta gamehub con argumentos (y, si se da, texto por la entrada estándar). */
function run(args, cwd, input) {
  const [program, ...prefix] = command();
  return new Promise((resolve) => {
    let child;
    try {
      child = cp.spawn(program, [...prefix, ...args], { cwd });
    } catch (error) {
      resolve({ code: -1, stdout: "", stderr: String(error) });
      return;
    }
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", (error) => resolve({ code: -1, stdout, stderr: String(error) }));
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    if (input !== undefined) {
      child.stdin.end(input);
    }
  });
}

/** Un diagnóstico de `gamehub check --format json` como diagnóstico de VS Code. */
function toDiagnostic(item) {
  const line = Math.max((item.line || 1) - 1, 0);
  const column = Math.max((item.column || 1) - 1, 0);
  const endLine = Math.max((item.end_line || item.line || 1) - 1, line);
  let endColumn = Math.max((item.end_column || item.column || 1) - 1, 0);
  if (endLine === line && endColumn <= column) {
    endColumn = column + 1;
  }
  const range = new vscode.Range(line, column, endLine, endColumn);
  const details = [...(item.notes || []).map((n) => `nota: ${n}`)];
  if (item.help) {
    details.push(`ayuda: ${item.help}`);
  }
  const message = [item.message, ...details].join("\n");
  const severity =
    item.severity === "error" ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
  const diagnostic = new vscode.Diagnostic(range, message, severity);
  diagnostic.code = item.code;
  diagnostic.source = "nomos";
  return diagnostic;
}

async function check(document, collection, output) {
  if (document.languageId !== "nomos" || document.uri.scheme !== "file") {
    return;
  }
  const file = document.uri.fsPath;
  const result = await run(["check", "--format", "json", file], workingDirectory(document.uri));
  let items;
  try {
    items = JSON.parse(result.stdout);
  } catch {
    output.appendLine(`gamehub check falló (${result.code}): ${result.stderr || result.stdout}`);
    const message =
      "No se pudo ejecutar gamehub check. Revisa el ajuste nomos.command (salida: Nomos).";
    collection.set(document.uri, [
      new vscode.Diagnostic(new vscode.Range(0, 0, 0, 1), message, vscode.DiagnosticSeverity.Information),
    ]);
    return;
  }
  // Los diagnósticos pueden ser del propio archivo o de un módulo que importa.
  const byFile = new Map([[file, []]]);
  for (const item of items) {
    const target = item.file ? path.resolve(workingDirectory(document.uri), item.file) : file;
    if (!byFile.has(target)) {
      byFile.set(target, []);
    }
    byFile.get(target).push(toDiagnostic(item));
  }
  for (const [target, diagnostics] of byFile) {
    collection.set(vscode.Uri.file(target), diagnostics);
  }
}

function activate(context) {
  const collection = vscode.languages.createDiagnosticCollection("nomos");
  const output = vscode.window.createOutputChannel("Nomos");
  context.subscriptions.push(collection, output);

  const checkOnSave = () => vscode.workspace.getConfiguration("nomos").get("checkOnSave", true);
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((d) => checkOnSave() && check(d, collection, output)),
    vscode.workspace.onDidSaveTextDocument((d) => checkOnSave() && check(d, collection, output)),
    vscode.workspace.onDidCloseTextDocument((d) => collection.delete(d.uri)),
    vscode.commands.registerCommand("nomos.check", () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        check(editor.document, collection, output);
      }
    }),
    vscode.languages.registerDocumentFormattingEditProvider("nomos", {
      async provideDocumentFormattingEdits(document) {
        const text = document.getText();
        const result = await run(["fmt", "--stdin"], workingDirectory(document.uri), text);
        if (result.code !== 0) {
          output.appendLine(result.stderr || result.stdout);
          vscode.window.setStatusBarMessage("Nomos: no se puede formatear (hay errores de sintaxis)", 4000);
          return [];
        }
        if (result.stdout === text) {
          return [];
        }
        const whole = new vscode.Range(document.positionAt(0), document.positionAt(text.length));
        return [vscode.TextEdit.replace(whole, result.stdout)];
      },
    })
  );
  for (const document of vscode.workspace.textDocuments) {
    if (checkOnSave()) {
      check(document, collection, output);
    }
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
