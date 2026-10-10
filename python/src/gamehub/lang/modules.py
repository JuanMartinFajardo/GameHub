# SPDX-License-Identifier: Apache-2.0
"""Módulos de Nomos: `import a.b.{X, Y}` e `import a.b.*`.

- Resolución de `a.b`: `std.…` es la biblioteca estándar (`stdlib/std/…`); después, una
  dependencia `a` del paquete del archivo (`game.toml`, ver `gamehub.packages`); si no, relativo
  al directorio del archivo que importa (`a/b.game`).
- Un módulo aporta sus declaraciones de primer nivel: `enum`, `struct`, `fn` y juegos (para
  `extends` y los combinadores). Sus funciones no leen el estado de ningún juego: son funciones
  puras de sus argumentos.
- `import m.{X}` trae `X` y lo que `X` necesita del módulo (sus tipos y funciones auxiliares);
  `import m.*` trae todo lo que declara el propio módulo. Lo importado solo llega a la IR si el
  juego lo usa.
"""

from __future__ import annotations

import dataclasses
import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gamehub.lang import ast
from gamehub.lang.diagnostics import Diagnostics
from gamehub.lang.parser import parse
from gamehub.lang.source import Source, Span
from gamehub.packages import (
    MANIFEST,
    Locked,
    Manifest,
    PackageError,
    dependency_root,
    load_lock,
    load_manifest,
)

Decl = ast.EnumDecl | ast.StructDecl | ast.FnDecl | ast.GameDecl | ast.GameAlias
STD = "std"


def stdlib_dir() -> Path:
    """Directorio `stdlib/` (contiene `std/`). Se puede forzar con GAMEHUB_STDLIB_DIR."""
    override = os.environ.get("GAMEHUB_STDLIB_DIR")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "stdlib"
        if (candidate / STD).is_dir():
            return candidate
    raise FileNotFoundError("No se encuentra stdlib/std; define GAMEHUB_STDLIB_DIR")


@dataclass
class Module:
    name: str
    path: Path
    file: ast.File
    #: Declaraciones escritas en el propio módulo.
    own: dict[str, Decl] = field(default_factory=dict)
    #: Lo que el módulo tiene a mano: lo suyo y lo que importa (nombre → declaración, módulo).
    available: dict[str, tuple[Decl, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Imported:
    name: str
    decl: Decl
    module: str


class Loader:
    """Carga módulos (cada archivo una sola vez) y resuelve los `import` de un archivo."""

    def __init__(self, diagnostics: Diagnostics) -> None:
        self.diagnostics = diagnostics
        self.cache: dict[Path, Module] = {}
        self.loading: list[tuple[Path, str]] = []
        self.manifests: dict[Path, Manifest | None] = {}
        self.lock: dict[str, Locked] = {}

    def root_imports(self, file: ast.File, source: Source) -> list[Imported]:
        """Los `import` del archivo que se compila (que cuenta para detectar ciclos). Su paquete
        aporta el lock con el que se resuelven todas las dependencias git."""
        if source.path is None:
            return self.imports(file, source)
        try:
            manifest = self.manifest_for(source.path)
            if manifest is not None:
                self.lock = load_lock(manifest.root)
        except PackageError as exc:
            span = file.imports[0].span if file.imports else file.span
            self.diagnostics.error("E507", str(exc), span)
            return []
        self.loading.append((source.path.resolve(), source.path.stem))
        try:
            return self.imports(file, source)
        finally:
            self.loading.pop()

    def imports(self, file: ast.File, source: Source) -> list[Imported]:
        """Todo lo que importan los `import` de un archivo (sin repetir)."""
        found: dict[str, Imported] = {}
        for imp in file.imports:
            for item in self.import_names(imp, source):
                previous = found.get(item.name)
                if previous is not None and previous.decl is not item.decl:
                    self.diagnostics.error(
                        "E202",
                        f"`{item.name}` se importa de dos módulos: {previous.module} y "
                        f"{item.module}",
                        imp.span,
                    )
                    continue
                found[item.name] = item
        return list(found.values())

    def import_names(self, imp: ast.Import, source: Source) -> list[Imported]:
        module = self.load(imp.path, source, imp.span)
        if module is None:
            return []
        if imp.names is None:
            wanted = list(module.own)
        else:
            wanted = []
            for name in imp.names:
                if name in module.available:
                    wanted.append(name)
                    continue
                close = difflib.get_close_matches(name, list(module.available), n=1, cutoff=0.6)
                self.diagnostics.error(
                    "E201",
                    f"el módulo {module.name} no tiene `{name}`",
                    imp.span,
                    help=f"¿quisiste decir `{close[0]}`?" if close else None,
                )
        return _closure(module, wanted)

    # --- carga ----------------------------------------------------------------------------------

    def manifest_for(self, path: Path) -> Manifest | None:
        """El manifiesto del paquete de un archivo (subiendo directorios), con caché."""
        for directory in [path.resolve().parent, *path.resolve().parent.parents]:
            if directory in self.manifests:
                return self.manifests[directory]
            if (directory / MANIFEST).is_file():
                manifest = load_manifest(directory)
                self.manifests[directory] = manifest
                return manifest
        return None

    def resolve(self, parts: list[str], source: Source) -> Path:
        """Archivo de un módulo. En un `import` cada parte es un identificador, así que
        `prisoners_dilemma` también encuentra `prisoners-dilemma.game` (el nombre habitual de
        los archivos de juego)."""
        if parts[0] == STD:
            return stdlib_dir().joinpath(*parts).with_suffix(".game")
        if source.path is not None:
            manifest = self.manifest_for(source.path)
            dep = manifest.dependency(parts[0]) if manifest is not None else None
            if manifest is not None and dep is not None:
                root = dependency_root(manifest, dep, self.lock)
                if len(parts) > 1:
                    return _module_file(root, parts[1:])
                if (root / MANIFEST).is_file():
                    return load_manifest(root).entry_path
                return root / f"{dep.name}.game"
        base = source.path.parent if source.path is not None else Path.cwd()
        return _module_file(base, parts)

    def load(self, parts: list[str], source: Source, span: Span) -> Module | None:
        name = ".".join(parts)
        try:
            path = self.resolve(parts, source)
        except FileNotFoundError as exc:
            self.diagnostics.error("E503", f"no se puede cargar {name}: {exc}", span)
            return None
        except PackageError as exc:
            self.diagnostics.error("E507", str(exc), span)
            return None
        if not path.is_file():
            where = "la biblioteca estándar" if parts[0] == STD else str(path.parent)
            self.diagnostics.error(
                "E503",
                f"módulo no encontrado: {name}",
                span,
                help=f"se buscó {path.name} en {where}",
            )
            return None
        path = path.resolve()
        if any(p == path for p, _ in self.loading):
            chain = " → ".join([*(n for _, n in self.loading), name])
            self.diagnostics.error("E504", f"importación circular: {chain}", span)
            return None
        if path in self.cache:
            return self.cache[path]
        display = "/".join(parts) + ".game" if parts[0] == STD else str(path)
        module_source = Source(display, path.read_text(encoding="utf-8"), path)
        self.loading.append((path, name))
        try:
            tree = parse(module_source, self.diagnostics)
            module = Module(name, path, tree)
            for item in tree.items:
                if isinstance(item, Decl):
                    if item.name in module.own:
                        self.diagnostics.error(
                            "E202", f"declaración duplicada: {item.name}", item.span
                        )
                        continue
                    module.own[item.name] = item
            for item in self.imports(tree, module_source):
                module.available[item.name] = (item.decl, item.module)
            for decl_name, decl in module.own.items():
                module.available[decl_name] = (decl, name)
        finally:
            self.loading.pop()
        self.cache[path] = module
        return module


def _module_file(base: Path, parts: list[str]) -> Path:
    path = base.joinpath(*parts).with_suffix(".game")
    if not path.is_file():
        hyphenated = base.joinpath(*(p.replace("_", "-") for p in parts)).with_suffix(".game")
        if hyphenated.is_file():
            return hyphenated
    return path


def _closure(module: Module, wanted: list[str]) -> list[Imported]:
    """Los nombres pedidos y, transitivamente, lo que necesitan del módulo."""
    owners: dict[str, list[str]] = {}
    for name, (decl, _) in module.available.items():
        if isinstance(decl, ast.EnumDecl):
            for value in decl.values:
                owners.setdefault(value, []).append(name)
    result: dict[str, Imported] = {}
    stack = list(reversed(wanted))
    while stack:
        name = stack.pop()
        if name in result or name not in module.available:
            continue
        decl, origin = module.available[name]
        result[name] = Imported(name, decl, origin)
        for ref in sorted(references(decl)):
            stack.append(ref)
            stack.extend(owners.get(ref, ()))
    # En el orden del módulo: primero lo que importa (las dependencias), luego lo suyo.
    order = {name: i for i, name in enumerate(module.available)}
    return sorted(result.values(), key=lambda item: order[item.name])


def references(node: Any) -> set[str]:
    """Identificadores que menciona un trozo de AST: nombres, funciones llamadas y tipos."""
    found: set[str] = set()

    def visit(x: Any) -> None:
        if isinstance(x, ast.Name):
            found.add(x.name)
        elif isinstance(x, ast.Call | ast.Aggregate):
            found.add(x.func)
        elif isinstance(x, ast.StructLit):
            found.add(x.type_name)
        elif isinstance(x, ast.TName | ast.TGeneric):
            found.add(x.name)
        elif isinstance(x, ast.GameDecl) and x.extends is not None:
            found.add(x.extends)
        elif isinstance(x, ast.GameAlias):
            found.add(x.base)
        if dataclasses.is_dataclass(x) and not isinstance(x, type):
            for f in dataclasses.fields(x):
                if f.name not in ("span", "trivia", "doc", "end_comments"):
                    visit(getattr(x, f.name))
        elif isinstance(x, list | tuple):
            for y in x:
                visit(y)
        elif isinstance(x, dict):
            for y in x.values():
                visit(y)

    visit(node)
    return found
