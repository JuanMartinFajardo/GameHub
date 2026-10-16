# Nomos for VS Code

Support for [GameHub](../../../README.md)'s **Nomos** language (`.game` files):

- Syntax **highlighting** (a TextMate grammar): keywords, node kinds, names of nodes, actions and
  functions, annotations (`@visible`…), documentation comments (`///`).
- **Diagnostics** from `gamehub check` on open and on save: errors and warnings with their
  position, note and help, including those of imported modules.
- **Formatting** with `gamehub fmt` (*Format Document*, or on save if you have
  `editor.formatOnSave`).
- Comments, brackets, automatic indentation and continuation of `///` when pressing Enter.

## Installation

It needs `gamehub` (this repository's Python package). To try the extension without packaging it:

```bash
ln -s "$PWD" ~/.vscode/extensions/gamehub.nomos-0.1.0
```

(from this directory) and restart VS Code. To package it: `npx @vscode/vsce package` and
`code --install-extension nomos-0.1.0.vsix`.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `nomos.command` | `["gamehub"]` | How to run gamehub. In the GameHub repository: `["uv", "run", "--project", "python", "gamehub"]`. |
| `nomos.checkOnSave` | `true` | Checks the file when it is opened and saved. |

The **Nomos: check the game** command checks it at any time.

## Language server

`gamehub lsp` is a complete language server (completion, hover, go to definition, references,
rename, formatting, quick fixes…) over standard input. This extension does not use it yet;
meanwhile, any editor with a generic LSP client (Neovim, Helix, Zed, or VS Code with a generic LSP
extension) can use it with the `gamehub lsp` command for `.game` files.
