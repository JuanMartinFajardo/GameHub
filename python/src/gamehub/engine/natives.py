# SPDX-License-Identifier: Apache-2.0
"""Plugins nativos: implementaciones rápidas de funciones de la IR (ADR-062).

Una función de la IR con `"native": "modulo.funcion"` tiene en su cuerpo la **implementación de
referencia**, que vale en cualquier motor. Un plugin nativo puede sustituirla si da exactamente
el mismo resultado para cualquier entrada (lo comprueban los tests diferenciales). Si no hay
plugin, o `GAMEHUB_NATIVES=0`, se usa la referencia: el juego es el mismo, solo más lento.

Los plugins son módulos **WebAssembly** (el mismo binario vale en Python, en el navegador y en el
motor C++), sin importaciones y con un límite de cómputo por llamada. ABI `gamehub-native/1`:

- El módulo exporta `memory`, `gh_buffer() -> i32` (dirección de un búfer de al menos 64 KiB) y
  una función por cada función nativa: `(in: i32, len: i32, out: i32) -> i32`.
- Los argumentos van al búfer como palabras i32 en orden: `Bool` 0/1, `Int` y `Seat` tal cual,
  un enumerado por su ordinal, un struct campo a campo, una tupla elemento a elemento, una lista
  como su longitud y sus elementos, un opcional como 0 (ninguno) o 1 y el valor. La función
  escribe el resultado, codificado igual, a partir de `out` y devuelve cuántas palabras escribió
  (negativo = error).
- El plugin del módulo `a.b` es el archivo `a.b.wasm` de un directorio de plugins:
  `stdlib/std/native/` y los de la variable `GAMEHUB_NATIVE_PATH` (separados por `:`). Junto a
  él puede estar su fuente en texto, `a.b.wat`.

También se pueden registrar implementaciones en Python con `register` (para probar o para
plugins escritos en Python dentro de un programa de confianza).
"""

from __future__ import annotations

import os
import struct
import threading
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path
from typing import Any

from gamehub.engine.errors import RuleError
from gamehub.engine.values import EnumValue, StructValue, Type, TypeTable

#: Cómputo máximo de una llamada a un plugin (unidades de «combustible» de wasmtime).
FUEL = 50_000_000

#: Palabras como mucho en el búfer de intercambio (64 KiB: la mitad para la entrada).
BUFFER_WORDS = 16384

NativeImpl = Callable[..., Any]

_registry: dict[str, NativeImpl] = {}


def register(native_id: str, impl: NativeImpl) -> None:
    """Registra una implementación en Python de la función nativa `native_id` (recibe y devuelve
    valores del motor). Tiene prioridad sobre los plugins WebAssembly."""
    _registry[native_id] = impl


def unregister(native_id: str) -> None:
    _registry.pop(native_id, None)


def enabled() -> bool:
    return os.environ.get("GAMEHUB_NATIVES", "1") not in ("0", "false", "no")


def search_path() -> list[Path]:
    from gamehub.lang.modules import stdlib_dir

    extra = [Path(p) for p in os.environ.get("GAMEHUB_NATIVE_PATH", "").split(os.pathsep) if p]
    return [*extra, stdlib_dir() / "std" / "native"]


def find_module(native_id: str) -> Path | None:
    """El archivo .wasm (o, si no hay, el .wat) del módulo de `native_id`."""
    module = native_id.rpartition(".")[0]
    for directory in search_path():
        for suffix in (".wasm", ".wat"):
            path = directory / f"{module}{suffix}"
            if path.is_file():
                return path
    return None


def resolve(
    native_id: str, params: Sequence[Type], returns: Type, types: TypeTable
) -> NativeImpl | None:
    """La implementación nativa de `native_id`, o None si no hay (o están desactivadas)."""
    if not enabled():
        return None
    if native_id in _registry:
        return _registry[native_id]
    path = find_module(native_id)
    if path is None or not wasm_available():
        return None
    module = _load(path)
    export = native_id.rpartition(".")[2]
    if export not in module.exports:
        return None
    return WasmFunction(module, export, tuple(params), returns, types)


# --- WebAssembly ----------------------------------------------------------------------------------


def wasm_available() -> bool:
    try:
        import wasmtime  # noqa: F401
    except ImportError:
        return False
    return True


def wat_to_wasm(text: str) -> bytes:
    """Compila un módulo en formato de texto (WAT) a binario."""
    import wasmtime

    return bytes(wasmtime.wat2wasm(text))


class WasmModule:
    """Un módulo cargado: una instancia propia, protegida por un cerrojo (una instancia de
    wasmtime no se puede usar desde dos hilos a la vez)."""

    def __init__(self, path: Path) -> None:
        import wasmtime

        config = wasmtime.Config()
        config.consume_fuel = True
        self.engine = wasmtime.Engine(config)
        binary = path.read_bytes() if path.suffix == ".wasm" else wat_to_wasm(path.read_text())
        module = wasmtime.Module(self.engine, binary)
        if module.imports:
            raise RuleError(f"el plugin nativo {path.name} importa funciones: no está permitido")
        self.store = wasmtime.Store(self.engine)
        self.store.set_fuel(FUEL)
        instance = wasmtime.Instance(self.store, module, [])
        exports = instance.exports(self.store)
        memory = exports["memory"]
        buffer = exports["gh_buffer"]
        assert isinstance(memory, wasmtime.Memory) and isinstance(buffer, wasmtime.Func)
        self.memory = memory
        self.functions: dict[str, wasmtime.Func] = {}
        for e in module.exports:
            item = exports[e.name]
            if isinstance(item, wasmtime.Func):
                self.functions[e.name] = item
        self.exports = set(self.functions)
        self.buffer = int(buffer(self.store))
        self.lock = threading.Lock()
        self.path = path

    def call(self, export: str, words: list[int]) -> list[int]:
        if len(words) > BUFFER_WORDS // 2:
            raise RuleError(f"plugin nativo {self.path.name}: la entrada es demasiado grande")
        out = self.buffer + 4 * (BUFFER_WORDS // 2)
        data = struct.pack(f"<{len(words)}i", *words)
        with self.lock:
            self.memory.write(self.store, data, self.buffer)
            self.store.set_fuel(FUEL)
            try:
                n = self.functions[export](self.store, self.buffer, len(words), out)
            except Exception as exc:  # trampa del módulo o sin combustible
                raise RuleError(f"el plugin nativo {self.path.name} ha fallado: {exc}") from None
            if not isinstance(n, int) or n < 0 or n > BUFFER_WORDS // 2:
                raise RuleError(f"el plugin nativo {self.path.name} devolvió un error ({n})")
            raw = self.memory.read(self.store, out, out + 4 * n)
        return list(struct.unpack(f"<{n}i", raw))


@cache
def _load(path: Path) -> WasmModule:
    return WasmModule(path)


class WasmFunction:
    """Una función nativa de un módulo: codifica los argumentos, llama y decodifica."""

    def __init__(
        self,
        module: WasmModule,
        export: str,
        params: tuple[Type, ...],
        returns: Type,
        types: TypeTable,
    ) -> None:
        self.module = module
        self.export = export
        self.params = params
        self.returns = returns
        self.codec = Codec(types)

    def __call__(self, *args: Any) -> Any:
        words: list[int] = []
        for value, t in zip(args, self.params, strict=True):
            self.codec.encode(value, t, words)
        result = self.module.call(self.export, words)
        value, used = self.codec.decode(result, 0, self.returns)
        if used != len(result):
            raise RuleError(f"el plugin nativo {self.module.path.name} devolvió palabras de más")
        return value


class Codec:
    """Valores del motor ↔ palabras i32 (ABI gamehub-native/1)."""

    def __init__(self, types: TypeTable) -> None:
        self.types = types

    def encode(self, v: Any, t: Type, out: list[int]) -> None:
        match t.kind:
            case "prim":
                if t.name == "Cell":
                    out.extend(_word(x) for x in v)
                elif t.name == "Bool":
                    out.append(1 if v else 0)
                else:
                    out.append(_word(v))
            case "enum":
                assert isinstance(v, EnumValue)
                out.append(v.ordinal)
            case "struct":
                assert isinstance(v, StructValue)
                for (_, x), (_, ft) in zip(v.fields, self.types.structs[t.name], strict=True):
                    self.encode(x, ft, out)
            case "tuple":
                for x, xt in zip(v, t.args, strict=True):
                    self.encode(x, xt, out)
            case "list":
                out.append(len(v))
                for x in v:
                    self.encode(x, t.inner, out)
            case "option":
                if v is None:
                    out.append(0)
                else:
                    out.append(1)
                    self.encode(v, t.inner, out)
            case _:
                raise RuleError(f"un plugin nativo no admite el tipo {t.kind}")

    def decode(self, words: list[int], i: int, t: Type) -> tuple[Any, int]:
        def take() -> int:
            if i >= len(words):
                raise RuleError("el plugin nativo devolvió un resultado incompleto")
            return words[i]

        match t.kind:
            case "prim":
                if t.name == "Cell":
                    r, i = take(), i + 1
                    c, i = take(), i + 1
                    return (r, c), i
                w = take()
                return (w != 0 if t.name == "Bool" else w), i + 1
            case "enum":
                values = self.types.enums[t.name]
                w = take()
                if not 0 <= w < len(values):
                    raise RuleError(f"el plugin nativo devolvió un {t.name} inválido ({w})")
                return values[w], i + 1
            case "struct":
                fields = []
                for name, ft in self.types.structs[t.name]:
                    x, i = self.decode(words, i, ft)
                    fields.append((name, x))
                return StructValue(t.name, tuple(fields)), i
            case "tuple":
                items = []
                for xt in t.args:
                    x, i = self.decode(words, i, xt)
                    items.append(x)
                return tuple(items), i
            case "list":
                n, i = take(), i + 1
                items = []
                for _ in range(n):
                    x, i = self.decode(words, i, t.inner)
                    items.append(x)
                return tuple(items), i
            case "option":
                flag, i = take(), i + 1
                if flag == 0:
                    return None, i
                return self.decode(words, i, t.inner)
        raise RuleError(f"un plugin nativo no admite el tipo {t.kind}")


def _word(x: Any) -> int:
    if isinstance(x, bool) or not isinstance(x, int) or not -(2**31) <= x < 2**31:
        raise OverflowError(x)
    return x


# --- Comprobación diferencial ---------------------------------------------------------------------


def random_value(t: Type, types: TypeTable, rng: Any, depth: int = 0) -> Any:
    """Un valor al azar del tipo `t` (enteros pequeños, listas de 0 a 9 elementos) para comparar
    un plugin con su referencia."""
    match t.kind:
        case "prim":
            if t.name == "Bool":
                return rng.random() < 0.5
            if t.name == "Cell":
                return (rng.randint(-2, 9), rng.randint(-2, 9))
            return rng.randint(-20, 60)
        case "enum":
            return rng.choice(types.enums[t.name])
        case "struct":
            fields = types.structs[t.name]
            return StructValue(
                t.name, tuple((n, random_value(ft, types, rng, depth + 1)) for n, ft in fields)
            )
        case "tuple":
            return tuple(random_value(a, types, rng, depth + 1) for a in t.args)
        case "list":
            n = rng.randint(0, 9 if depth < 2 else 3)
            return tuple(random_value(t.inner, types, rng, depth + 1) for _ in range(n))
        case "option":
            return None if rng.random() < 0.2 else random_value(t.inner, types, rng, depth + 1)
    raise ValueError(f"tipo no admitido: {t.kind}")


def stdlib_natives() -> dict[str, Path]:
    """Las funciones nativas de la biblioteca estándar: id → archivo del módulo de Nomos."""
    from gamehub.lang.modules import stdlib_dir

    found: dict[str, Path] = {}
    for path in sorted((stdlib_dir() / "std").glob("*.game")):
        for item in _module_ir(path)["functions"]:
            if "native" in item:
                found[item["native"]] = path
    return found


def _module_ir(path: Path) -> dict[str, Any]:
    from gamehub.lang.compiler import compile_file

    result = compile_file(path)
    if not result.ok or result.module is None:
        raise RuntimeError(f"{path} no es un módulo que compile")
    return result.module


def module_game(path: Path, *, natives: bool = True) -> Any:
    """Un `GameDef` mínimo con los tipos y las funciones de un módulo (para llamarlas)."""
    from gamehub.engine.game import GameDef

    module = _module_ir(path)
    ir = {
        "ir_version": "0.1.0",
        "game": {"id": "module", "version": "0.0.0"},
        "players": {"min": 1, "max": 1},
        "types": module["types"],
        "state": [],
        "functions": module["functions"],
        "flow": {
            "start": "End",
            "nodes": [{"id": "End", "kind": "terminal", "payoff": ["fill", ["const", 0]]}],
        },
    }
    return GameDef(ir, natives=natives)


def call_function(defn: Any, name: str, args: dict[str, Any], *, reference: bool = False) -> Any:
    """Llama a una función de un `GameDef` con valores del motor (la nativa, si la hay, o su
    referencia)."""
    from gamehub.engine.env import Ctx, Env

    fn = defn.functions[name]
    body = fn.reference if reference and fn.reference is not None else fn.body
    return body(Env(Ctx(defn, (), {"num_players": 1}, 1), args=dict(args)))


def compare_with_reference(native_id: str, trials: int, seed: int = 0) -> list[str]:
    """Llama a la función nativa y a su referencia con `trials` entradas al azar y devuelve las
    diferencias (vacío si coinciden siempre). Falla si no hay plugin para `native_id`."""
    import random

    path = stdlib_natives()[native_id]
    defn = module_game(path)
    spec = next(f for f in defn.ir["functions"] if f.get("native") == native_id)
    name = spec["name"]
    fn = defn.functions[name]
    if fn.body is fn.reference:
        raise RuntimeError(f"no hay plugin nativo para {native_id}")
    params = [(p, defn.types.parse(t)) for p, t in spec["params"]]
    rng = random.Random(seed)
    problems: list[str] = []
    for _ in range(trials):
        args = {p: random_value(t, defn.types, rng) for p, t in params}
        results = []
        for reference in (False, True):
            try:
                results.append(("ok", call_function(defn, name, args, reference=reference)))
            except RuleError:
                results.append(("error", None))
        if results[0] != results[1]:
            problems.append(
                f"{name}({args}): nativo {results[0][1]!r}, referencia {results[1][1]!r}"
            )
            if len(problems) >= 10:
                break
    return problems


def build(write: bool) -> list[str]:
    """Compila cada `.wat` de la biblioteca estándar a su `.wasm`. Con `write=False`, solo dice
    cuáles no están al día (para el CI)."""
    from gamehub.lang.modules import stdlib_dir

    stale: list[str] = []
    for wat in sorted((stdlib_dir() / "std" / "native").glob("*.wat")):
        binary = wat_to_wasm(wat.read_text(encoding="utf-8"))
        wasm = wat.with_suffix(".wasm")
        if not wasm.is_file() or wasm.read_bytes() != binary:
            stale.append(wasm.name)
            if write:
                wasm.write_bytes(binary)
    return stale
