# SPDX-License-Identifier: Apache-2.0
"""El núcleo C++ compilado a WebAssembly (Emscripten) para el navegador: `@gamehub/engine`.

Los binarios (`gamehub-core.mjs`, `gamehub-core.wasm`, sus tipos y los plugins nativos de la
stdlib) se guardan en `web/packages/engine/wasm/` para que la parte web no necesite Emscripten.
`BUILD.json` lleva la huella SHA-256 de las fuentes con las que se compilaron: `check()` (y los
tests) avisan si el C++ ha cambiado sin recompilar; `build()` recompila (necesita el SDK de
Emscripten: `emcmake` en el PATH, o `$EMSDK`, o `~/emsdk`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Los artefactos de la compilación: (origen en el directorio de compilación, destino).
ARTIFACTS = (
    ("gamehub-core.mjs", "gamehub-core.mjs"),
    ("gamehub-core.wasm", "gamehub-core.wasm"),
    # TypeScript busca los tipos de un `.mjs` en un `.d.mts`.
    ("gamehub-core.d.ts", "gamehub-core.d.mts"),
)


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "core" / "CMakeLists.txt").is_file() and (parent / "web").is_dir():
            return parent
    raise FileNotFoundError("no se encuentra la raíz del repositorio (core/ y web/)")


def output_dir() -> Path:
    return repo_root() / "web" / "packages" / "engine" / "wasm"


def sources() -> list[Path]:
    """Lo que entra en el binario: el C++ del núcleo, sus enlaces con JavaScript y los plugins
    nativos de la stdlib (se copian junto a él)."""
    root = repo_root()
    core = root / "core"
    found = [core / "CMakeLists.txt"]
    for pattern in ("src/*.cpp", "include/gamehub/*.hpp", "wasm/*.cpp"):
        found.extend(core.glob(pattern))
    found.extend((root / "stdlib" / "std" / "native").glob("*.wasm"))
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def fingerprint() -> str:
    root = repo_root()
    digest = hashlib.sha256()
    for path in sources():
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        # Sin depender de los finales de línea del sistema.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def natives() -> list[Path]:
    return sorted((repo_root() / "stdlib" / "std" / "native").glob("*.wasm"))


def natives_index() -> Path:
    return repo_root() / "web" / "packages" / "engine" / "src" / "natives.gen.ts"


def render_natives_index() -> str:
    """El índice de plugins para el paquete web: una URL estática por módulo (así el empaquetador
    los copia como recursos)."""
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generado por `gamehub wasm --write`: los plugins nativos de la stdlib (ABI",
        "// gamehub-native/1) que el núcleo puede usar en el navegador, por módulo.",
        "",
        "export const NATIVE_PLUGINS: Readonly<Record<string, () => URL>> = {",
    ]
    for plugin in natives():
        lines.append(
            f'  "{plugin.stem}": () => new URL("../wasm/natives/{plugin.name}", import.meta.url),'
        )
    lines.append("};")
    return "\n".join(lines) + "\n"


def check() -> list[str]:
    """Problemas: binarios ausentes o compilados con otras fuentes."""
    out = output_dir()
    problems = [
        f"falta {name}"
        for name in [dest for _, dest in ARTIFACTS] + [f"natives/{p.name}" for p in natives()]
        if not (out / name).is_file()
    ]
    index = natives_index()
    if not index.is_file() or index.read_text(encoding="utf-8") != render_natives_index():
        problems.append(f"{index.name} desactualizado")
    stamp = out / "BUILD.json"
    if not stamp.is_file():
        return [*problems, "falta BUILD.json"]
    built = json.loads(stamp.read_text(encoding="utf-8")).get("sources")
    if built != fingerprint():
        problems.append("las fuentes del núcleo han cambiado desde la última compilación")
    return problems


def emscripten_env() -> dict[str, str]:
    """El entorno con Emscripten (`emcmake` en el PATH)."""
    env = dict(os.environ)
    if shutil.which("emcmake", path=env.get("PATH")):
        return env
    for base in (os.environ.get("EMSDK"), str(Path.home() / "emsdk")):
        if not base:
            continue
        script = Path(base) / "emsdk_env.sh"
        if script.is_file():
            dump = subprocess.run(
                ["bash", "-c", f'source "{script}" >/dev/null 2>&1 && env -0'],
                capture_output=True,
                check=True,
            ).stdout
            pairs = (item.split("=", 1) for item in dump.decode().split("\0") if "=" in item)
            return dict(pairs)
    raise FileNotFoundError(
        "no se encuentra Emscripten: instala el SDK (https://emscripten.org) y añade emcmake "
        "al PATH, o define EMSDK"
    )


def build(*, verbose: bool = False) -> Path:
    """Compila el núcleo con Emscripten y copia los binarios y los plugins a `output_dir()`."""
    root = repo_root()
    env = emscripten_env()
    build_dir = root / "core" / "build-wasm"
    tools = Path(sys.executable).parent
    cmake = shutil.which("cmake", path=f"{tools}{os.pathsep}{env.get('PATH', '')}") or "cmake"
    ninja = shutil.which("ninja", path=f"{tools}{os.pathsep}{env.get('PATH', '')}")
    configure = ["emcmake", cmake, "-S", str(root / "core"), "-B", str(build_dir)]
    configure += ["-DCMAKE_BUILD_TYPE=Release"]
    if ninja:
        configure += ["-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja}"]
    for command in (configure, [cmake, "--build", str(build_dir), "--target", "gamehub_core_wasm"]):
        done = subprocess.run(command, env=env, capture_output=not verbose, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"falló {' '.join(command[:2])}:\n{done.stdout}{done.stderr}")
    out = output_dir()
    (out / "natives").mkdir(parents=True, exist_ok=True)
    for source, dest in ARTIFACTS:
        shutil.copyfile(build_dir / source, out / dest)
    for old in (out / "natives").glob("*.wasm"):
        old.unlink()
    for plugin in natives():
        shutil.copyfile(plugin, out / "natives" / plugin.name)
    natives_index().write_text(render_natives_index(), encoding="utf-8")
    version = subprocess.run(
        ["emcc", "--version"], env=env, capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]
    stamp = {
        "sources": fingerprint(),
        "emscripten": version,
        "natives": [p.stem for p in natives()],
    }
    (out / "BUILD.json").write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return out
