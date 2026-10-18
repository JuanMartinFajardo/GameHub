# SPDX-License-Identifier: AGPL-3.0-or-later
"""Las órdenes del hub en la CLI: `gamehub hub serve`, `login`, `publish`, `pr`, `search`… y la
parte del hub de `clone` y `fork` (cuando el origen es `dueño/nombre`)."""

from __future__ import annotations

import argparse
import getpass
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from gamehub.hub import DEFAULT_PORT
from gamehub.hub.client import ClientError, Hub

HUB_REF = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")


def register(commands: Any) -> None:
    hub = commands.add_parser("hub", help="el hub: servidor, búsqueda y propuestas de cambio")
    sub = hub.add_subparsers(dest="hub_command", required=True)

    serve = sub.add_parser("serve", help="arranca un hub (API, git, salas y web)")
    serve.add_argument("--data", type=Path, default=Path("hub-data"), help="directorio de datos")
    serve.add_argument("--config", type=Path, help="hub.toml (opcional)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--public-url", help="la dirección con la que lo ven los demás")
    serve.add_argument("--workers", type=int, help="procesos de trabajos a la vez (1)")
    serve.add_argument("--admin", action="append", default=[], help="cuenta de moderación")
    serve.add_argument("--database", help="URL de la base de datos (SQLite por defecto)")
    serve.set_defaults(handler=_serve)

    search = sub.add_parser("search", help="busca juegos (texto y propiedades)")
    search.add_argument(
        "query", nargs="*", help='p. ej. "2 jugadores suma cero información perfecta"'
    )
    _hub_arg(search)
    search.set_defaults(handler=_search)

    whoami = sub.add_parser("whoami", help="con qué cuenta estás en el hub")
    _hub_arg(whoami)
    whoami.set_defaults(handler=_whoami)

    pr = sub.add_parser("pr", help="propuestas de cambio")
    prs = pr.add_subparsers(dest="pr_command", required=True)
    create = prs.add_parser("create", help="propone la rama actual al repositorio original")
    create.add_argument("--title", required=True)
    create.add_argument("--body", default="")
    create.add_argument("--repo", help="repositorio de destino (por defecto, el original del fork)")
    create.add_argument("--base", help="rama de destino (por defecto, la principal)")
    create.add_argument("--head", help="rama propuesta (por defecto, la actual, que se empuja)")
    create.add_argument("--dir", type=Path, default=Path("."))
    _hub_arg(create)
    create.set_defaults(handler=_pr_create)
    for name, help_text, handler in (
        ("show", "una propuesta con su diff semántico y su balance", _pr_show),
        ("merge", "fusiona una propuesta", _pr_merge),
        ("close", "cierra una propuesta sin fusionarla", _pr_close),
    ):
        p = prs.add_parser(name, help=help_text)
        p.add_argument("number", type=int)
        p.add_argument("--repo", help="dueño/nombre (por defecto, el del directorio)")
        p.add_argument("--dir", type=Path, default=Path("."))
        _hub_arg(p)
        p.set_defaults(handler=handler)
    listing = prs.add_parser("list", help="las propuestas de un repositorio")
    listing.add_argument("--repo")
    listing.add_argument("--state", default="open", choices=["open", "merged", "closed", "all"])
    listing.add_argument("--dir", type=Path, default=Path("."))
    _hub_arg(listing)
    listing.set_defaults(handler=_pr_list)

    login = commands.add_parser("login", help="entra en un hub y guarda un token para la CLI")
    login.add_argument("--hub", help=f"URL del hub (p. ej. http://localhost:{DEFAULT_PORT})")
    login.add_argument("--user", help="nombre de cuenta")
    login.add_argument("--token", help="un token ya creado en la web (en vez de la contraseña)")
    login.add_argument(
        "--password-stdin", action="store_true", help="lee la contraseña de la entrada estándar"
    )
    login.set_defaults(handler=_login)

    logout = commands.add_parser("logout", help="olvida el token de un hub")
    _hub_arg(logout)
    logout.set_defaults(handler=_logout)

    publish = commands.add_parser(
        "publish", help="publica una versión del paquete en el hub (semver automático)"
    )
    publish.add_argument("dir", nargs="?", type=Path, default=Path("."), metavar="DIR")
    publish.add_argument("--repo", help="dueño/nombre (si no, el remoto del hub o tu/paquete)")
    publish.add_argument("--version", help="la versión (si no, la que exige el cambio)")
    publish.add_argument("--notes", default="", help="notas de la versión")
    publish.add_argument("--dry-run", action="store_true", help="dice qué versión sería")
    _hub_arg(publish)
    publish.set_defaults(handler=_publish)


def _hub_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hub", help="URL del hub (si no, GAMEHUB_HUB o el de `gamehub login`)")


def _fail(text: str) -> int:
    print(f"error: {text}", file=sys.stderr)
    return 1


# --- servidor -----------------------------------------------------------------------------------


def _serve(args: argparse.Namespace) -> int:
    import asyncio

    from gamehub.hub.app import HubApp, hub_web_dir
    from gamehub.hub.config import HubConfig
    from gamehub.hub.service import Hub as HubService
    from gamehub.server.run import start, stop
    from gamehub.server.serve import until_stopped

    try:
        config = HubConfig.load(
            args.data.resolve(),
            args.config,
            public_url=args.public_url,
            workers=args.workers,
            database=args.database,
            admins=tuple(args.admin) or None,
        )
    except ValueError as exc:
        return _fail(str(exc))
    service = HubService(config)
    web = hub_web_dir()
    app = HubApp(service, web=web).app()

    async def main() -> None:
        server, task = await start(app, args.host, args.port)
        url = config.public_url or f"http://{args.host}:{server.port}"
        print(f"GameHub en {url}  (datos: {config.data})")
        if web is None:
            print("  sin la app web: compílala con `pnpm build` en la raíz del repositorio")
        print("  Ctrl+C para parar")
        try:
            await until_stopped()
        finally:
            await stop(server, task)

    try:
        asyncio.run(main())
    finally:
        service.close()
    return 0


# --- sesión -------------------------------------------------------------------------------------


def _login(args: argparse.Namespace) -> int:
    from gamehub.hub import client

    try:
        url = client.normalize_url(args.hub) if args.hub else client.hub_url(None)
    except ClientError as exc:
        return _fail(str(exc))
    if args.token:
        hub = Hub(url, token=args.token)
        try:
            me = hub.get("/me")["user"]
        except ClientError as exc:
            return _fail(str(exc))
        client.save_token(url, me["name"], args.token)
        print(f"✓ en {url} como {me['name']}")
        return 0
    user = args.user or input("Usuario: ").strip()
    password = (
        sys.stdin.readline().rstrip("\n")
        if args.password_stdin
        else getpass.getpass("Contraseña: ")
    )
    try:
        done = client.login(url, user, password)
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ en {done['url']} como {done['user']} (token guardado en {client.config_path()})")
    return 0


def _logout(args: argparse.Namespace) -> int:
    from gamehub.hub import client

    try:
        url = client.logout(args.hub)
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ fuera de {url}")
    return 0


def _whoami(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub)
        me = hub.get("/me")["user"]
    except ClientError as exc:
        return _fail(str(exc))
    print(
        f"{me['name']} en {hub.url}"
        + (f" (organizaciones: {', '.join(me['orgs'])})" if me.get("orgs") else "")
    )
    return 0


# --- repositorios locales -----------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise ClientError(
            done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "git falló"
        )
    return done.stdout.strip()


def local_repo(hub: Hub, directory: Path) -> str | None:
    """El `dueño/nombre` del hub al que apunta un remoto del clon (hub, origin…)."""
    try:
        remotes = _git("remote", "-v", cwd=directory).splitlines()
    except (ClientError, FileNotFoundError):
        return None
    prefix = hub.url + "/"
    for line in remotes:
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith(prefix):
            name = parts[1][len(prefix) :].removesuffix(".git").strip("/")
            if HUB_REF.match(name):
                return name
    return None


def _publish(args: argparse.Namespace) -> int:
    from gamehub.packages import PackageError, load_manifest

    directory = args.dir.resolve()
    try:
        manifest = load_manifest(directory)
        hub = Hub(args.hub)
        if hub.token is None:
            return _fail("entra antes en el hub: gamehub login")
        if not (directory / ".git").exists():
            return _fail(
                f"{directory} no es un repositorio git: git init && git add -A && git commit -m …"
            )
        if _git("status", "--porcelain", cwd=directory):
            print("aviso: hay cambios sin confirmar; se publica el último commit", file=sys.stderr)
        full = args.repo or local_repo(hub, directory)
        if full is None:
            me = hub.get("/me")["user"]["name"]
            full = f"{me}/{manifest.name}"
        owner, name = full.split("/", 1)
        try:
            hub.get(f"/repos/{full}")
        except ClientError as exc:
            if exc.status != 404:
                raise
            hub.post("/repos", {"owner": owner, "name": name, "kind": "game"})
            print(f"✓ creado {full} en {hub.url}")
        url = hub.git_url(full)
        if local_repo(hub, directory) is None:
            _git("remote", "add", "hub", url, cwd=directory)
        branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=directory)
        commit = _git("rev-parse", "HEAD", cwd=directory)
        hub.git(
            "push",
            "--quiet",
            url,
            f"HEAD:refs/heads/{'main' if branch == 'HEAD' else branch}",
            cwd=directory,
        )
        body = {
            "ref": commit,
            "version": args.version,
            "notes": args.notes,
            "dry_run": args.dry_run,
        }
        result = hub.post(
            f"/repos/{full}/releases", {k: v for k, v in body.items() if v not in (None, "")}
        )
    except (ClientError, PackageError) as exc:
        return _fail(str(exc))
    if args.dry_run:
        if result["problems"]:
            for p in result["problems"]:
                print(f"✗ {p}")
            return 1
        level = result["level"]
        print(
            f"se publicaría {full}@{result['version']} (cambio {level}, "
            f"antes {result['previous'] or 'ninguna'})"
        )
        for c in result["interface_changes"]:
            print(f"  {c['op']} {c['path']}{' (incompatible)' if c['breaking'] else ''}")
        return 0
    print(
        f"✓ publicado {result['ref']}" + (f" (cambio {result['level']})" if result["level"] else "")
    )
    if result["rules_hash"]:
        print(f"  reglas {result['rules_hash'][:19]}…  interfaz {result['interface_hash'][:19]}…")
    print(f"  {hub.url}/{full}")
    return 0


def clone_from_hub(source: str, root: Path, hub_url: str | None = None) -> int:
    from gamehub.packages import MANIFEST, PackageError, fetch, load_manifest

    try:
        hub = Hub(hub_url)
        hub.get(f"/repos/{source}")
        hub.git("clone", "--quiet", hub.git_url(source), str(root))
        if (root / MANIFEST).is_file():
            fetch(load_manifest(root))
    except (ClientError, PackageError) as exc:
        return _fail(str(exc))
    print(f"✓ clonado {source} en {root}/")
    return 0


def fork_on_hub(source: str, root: Path, new_name: str | None, hub_url: str | None = None) -> int:
    try:
        hub = Hub(hub_url)
        if hub.token is None:
            return _fail("entra antes en el hub: gamehub login")
        fork = hub.post(f"/repos/{source}/forks", {"name": new_name} if new_name else {})
        hub.git("clone", "--quiet", hub.git_url(fork["full_name"]), str(root))
        _git("remote", "add", "upstream", hub.git_url(source), cwd=root)
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ {fork['full_name']} (fork de {source}) clonado en {root}/")
    print("  cambia lo que quieras, haz commit y propón: gamehub hub pr create --title …")
    return 0


# --- propuestas ---------------------------------------------------------------------------------


def _repo_for(args: argparse.Namespace, hub: Hub) -> str:
    full = args.repo or local_repo(hub, args.dir.resolve())
    if full is None:
        raise ClientError("¿qué repositorio? Usa --repo dueño/nombre o un clon del hub")
    return full


def _pr_create(args: argparse.Namespace) -> int:
    directory = args.dir.resolve()
    try:
        hub = Hub(args.hub)
        source = local_repo(hub, directory)
        if source is None:
            return _fail("este directorio no es un clon de un repositorio del hub")
        target = args.repo or hub.get(f"/repos/{source}")["parent"] or source
        head = args.head or _git("rev-parse", "--abbrev-ref", "HEAD", cwd=directory)
        if not args.head:
            hub.git(
                "push", "--quiet", hub.git_url(source), f"HEAD:refs/heads/{head}", cwd=directory
            )
        body = {
            "source": source,
            "head": head,
            "base": args.base,
            "title": args.title,
            "body": args.body,
        }
        pull = hub.post(f"/repos/{target}/pulls", {k: v for k, v in body.items() if v is not None})
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ propuesta #{pull['number']} en {target}: {pull['title']}")
    print(f"  {hub.url}/{target}/pulls/{pull['number']}")
    return 0


def _pr_list(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub)
        full = _repo_for(args, hub)
        found = hub.get(f"/repos/{full}/pulls", state=args.state)["pulls"]
    except ClientError as exc:
        return _fail(str(exc))
    for p in found:
        print(
            f"#{p['number']:<4} {p['state']:<7} {p['title']}  "
            f"({p['source']}:{p['head']} → {p['base']})"
        )
    if not found:
        print("ninguna")
    return 0


def _pr_show(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub)
        full = _repo_for(args, hub)
        pull = hub.get(f"/repos/{full}/pulls/{args.number}")
        diff = hub.get(f"/repos/{full}/pulls/{args.number}/diff")
    except ClientError as exc:
        return _fail(str(exc))
    print(f"#{pull['number']} {pull['title']} [{pull['state']}] de {pull['author']}")
    print(f"  {pull['source']}:{pull['head']} → {full}:{pull['base']}")
    files = diff["text"]["files"]
    print(
        f"Texto: {len(files)} archivo(s) "
        + ", ".join(f"{f['path']} (+{f['added']} −{f['removed']})" for f in files)
    )
    semantic = diff.get("semantic")
    if semantic and semantic.get("changes") is not None:
        print("Semántica:" + (" mismas reglas" if semantic.get("same_rules") else ""))
        for c in semantic["changes"]:
            print(f"  {c['op']} {c['path']}")
        if semantic.get("level"):
            print(f"  publicar exigiría un cambio {semantic['level']}")
    balance = pull.get("balance")
    if balance:
        print(f"Balance: {balance['status']}")
        if balance.get("result"):
            print(balance["result"]["markdown"])
    return 0


def _pr_merge(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub)
        full = _repo_for(args, hub)
        pull = hub.post(f"/repos/{full}/pulls/{args.number}/merge")
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ fusionada la propuesta #{pull['number']} ({pull['merge_commit'][:12]})")
    print(f"  publícala: gamehub publish --repo {full}  (o desde la web)")
    return 0


def _pr_close(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub)
        full = _repo_for(args, hub)
        hub.post(f"/repos/{full}/pulls/{args.number}/close")
    except ClientError as exc:
        return _fail(str(exc))
    print(f"✓ cerrada la propuesta #{args.number}")
    return 0


# --- buscar -------------------------------------------------------------------------------------


def _search(args: argparse.Namespace) -> int:
    try:
        hub = Hub(args.hub, token="")
        found = hub.get("/search", q=" ".join(args.query))
    except ClientError as exc:
        return _fail(str(exc))
    if found["filters"]:
        print("propiedades: " + ", ".join(f"{k}={v}" for k, v in found["filters"].items()))
    for r in found["results"]:
        rel = r.get("release")
        labels = " · ".join(rel["properties"].get("labels", [])) if rel else "sin versiones"
        version = f"@{rel['version']}" if rel else ""
        print(f"{r['full_name']}{version}  ★{r['stars']}  {labels}")
        if r["description"]:
            print(f"    {r['description']}")
    print(f"{found['total']} resultado(s)")
    return 0
