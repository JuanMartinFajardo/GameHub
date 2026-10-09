# SPDX-License-Identifier: Apache-2.0
"""Reglamento autogenerado (`gamehub rules`): un documento Markdown con todo lo que dice la IR
de un juego, en el orden en que lo necesita quien aprende a jugar: de qué va, qué se configura,
con qué se juega y quién ve qué, cómo transcurre la partida (con el diagrama) y cómo se gana.

Las reglas que no son texto (condiciones, efectos, pagos) se muestran en Nomos, que se lee bien;
los textos traducibles salen en el idioma pedido (o en el primero disponible).
"""

from __future__ import annotations

from typing import Any

from gamehub.analysis import classify, irwalk
from gamehub.lang.decompile import expression_text, function_text, statements_text, type_text
from gamehub.render.viz import KINDS, mermaid


def rules(ir: dict[str, Any], lang: str = "es") -> str:
    return _Rules(ir, lang).document()


class _Rules:
    def __init__(self, ir: dict[str, Any], lang: str) -> None:
        self.ir = ir
        self.lang = lang
        self.out: list[str] = []

    def text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            return value.get(self.lang) or next(iter(value.values()), "")
        return str(value)

    def code(self, expr: Any) -> str:
        text = " ".join(line.strip() for line in expression_text(self.ir, expr).splitlines())
        return f"`{text}`"

    def add(self, *lines: str) -> None:
        self.out.extend(lines)

    def document(self) -> str:
        ir = self.ir
        meta = ir.get("meta", {})
        title = self.text(meta.get("title")) or ir["game"]["id"]
        self.add(f"# {title}", "")
        if meta.get("description"):
            self.add(self.text(meta["description"]), "")
        labels = classify(ir).labels()
        facts = [f"**Tipo:** {' · '.join(labels)}", f"**Versión:** {ir['game']['version']}"]
        if meta.get("authors"):
            facts.append(f"**Autoría:** {', '.join(meta['authors'])}")
        if meta.get("license"):
            facts.append(f"**Licencia:** {meta['license']}")
        self.add(*(f"- {fact}" for fact in facts), "")
        self.params()
        self.types()
        self.state()
        self.flow()
        self.functions()
        self.add(
            "---",
            "",
            f"*Reglamento generado por `gamehub rules` a partir del juego `{ir['game']['id']}`.*",
        )
        return "\n".join(self.out).rstrip() + "\n"

    # --- secciones ------------------------------------------------------------------------------

    def params(self) -> None:
        params = self.ir.get("params", [])
        constraints = self.ir.get("constraints", [])
        if not params:
            return
        self.add("## Opciones de la partida", "")
        self.add("| Opción | Tipo | Por defecto | Qué es |", "|---|---|---|---|")
        for p in params:
            row = [
                f"`{p['name']}`",
                f"`{type_text(self.ir, p['type'])}`",
                self.code(p["default"]),
                self.text(p.get("doc")),
            ]
            self.add("| " + " | ".join(_cell(x) for x in row) + " |")
        self.add("")
        if constraints:
            self.add("Restricciones:", "")
            for c in constraints:
                message = self.text(c.get("message"))
                self.add(f"- {self.code(c['expr'])}" + (f" — {message}" if message else ""))
            self.add("")

    def types(self) -> None:
        types = self.ir.get("types", [])
        if not types:
            return
        self.add("## Componentes", "")
        for t in types:
            doc = self.text(t.get("doc"))
            suffix = f" — {doc}" if doc else ""
            if t["kind"] == "enum":
                values = ", ".join(t["values"])
                self.add(f"- **{t['name']}**: {values}{suffix}")
            else:
                fields = ", ".join(
                    f"{f['name']} (`{type_text(self.ir, f['type'])}`)" for f in t["fields"]
                )
                self.add(f"- **{t['name']}**: {fields}{suffix}")
        self.add("")

    def state(self) -> None:
        state = self.ir.get("state", [])
        if not state:
            return
        self.add("## Lo que hay sobre la mesa", "")
        self.add("| Elemento | Tipo | Al empezar | Quién lo ve |", "|---|---|---|---|")
        for v in state:
            row = [
                f"`{v['name']}`" + (f" — {self.text(v['doc'])}" if v.get("doc") else ""),
                f"`{type_text(self.ir, v['type'])}`",
                self.code(v["init"]),
                self.visibility(v),
            ]
            self.add("| " + " | ".join(_cell(x) for x in row) + " |")
        self.add("")

    def visibility(self, item: dict[str, Any]) -> str:
        shown = self.policy(item.get("visibility"))
        size = item.get("size_visibility")
        if item.get("visibility") not in (None, "all") and size is not None:
            shown += f" (cuántos: {self.policy(size)})"
        return shown

    def policy(self, vis: Any) -> str:
        if vis in (None, "all"):
            return "todos"
        if vis == "none":
            return "nadie"
        if vis == "owner":
            return "su dueño"
        if vis == {"when": ["item_face_up"]}:
            return "lo que está boca arriba"
        return f"si {self.code(vis['when'])}"

    def flow(self) -> None:
        flow = self.ir["flow"]
        self.add("## Desarrollo de la partida", "")
        self.add("```mermaid", mermaid(self.ir).rstrip(), "```", "")
        if flow.get("setup"):
            self.add(
                "**Preparación:**",
                "",
                "```game",
                statements_text(self.ir, flow["setup"]),
                "```",
                "",
            )
        self.add(f"La partida empieza en **{flow['start']}**.", "")
        for node, parent in irwalk.all_nodes(self.ir):
            self.node(node, parent)

    def node(self, node: dict[str, Any], parent: str | None) -> None:
        kind = node["kind"]
        where = f", dentro de la fase {parent}" if parent else ""
        self.add(f"### {node['id']} ({KINDS[kind]}{where})", "")
        if node.get("doc"):
            self.add(self.text(node["doc"]), "")
        match kind:
            case "decision":
                self.add(f"Juega {self.code(node['actor'])}.", "")
            case "simultaneous":
                self.add(f"Juegan a la vez, en secreto, {self.code(node['actors'])}.", "")
            case "window":
                modes = {
                    "priority": "por orden: el primero que no pase se lo queda",
                    "collect": "todos deciden en secreto; vale la primera respuesta según el orden",
                    "race": "el primero que actúe se lo queda",
                }
                mode = node.get("mode", "priority")
                order = f"; orden: {self.code(node['order'])}" if "order" in node else ""
                self.add(
                    f"Pueden responder {self.code(node['eligible'])} ({modes[mode]}{order}). "
                    "Pasar siempre está permitido.",
                    "",
                )
            case "chance":
                self.add("Decide el azar.", "")
            case "phase":
                self.add(f"Empieza en **{node['start']}**.", "")
                for key, label in (("on_enter", "Al entrar"), ("on_exit", "Al salir")):
                    if node.get(key):
                        self.block(label, node[key])
            case "terminal":
                self.add(f"**Fin de la partida.** Pagos: {self.code(node['payoff'])}.", "")
                if "rank" in node:
                    self.add(f"Clasificación: {self.code(node['rank'])}.", "")
        for action in node.get("actions", []):
            self.action(action)
        if node.get("effects"):
            self.block("Efectos", node["effects"])
        if node.get("resolve"):
            self.block("Al revelar las jugadas", node["resolve"])
        transitions = node.get("transitions", [])
        if transitions:
            intro = "Al salir de la fase" if kind == "phase" else "Después"
            self.add(f"{intro}:", "")
            for t in transitions:
                self.transition(t)
            self.add("")

    def action(self, action: dict[str, Any]) -> None:
        params = []
        for p in action.get("params", []):
            hidden = " (en secreto)" if p.get("visibility") not in (None, "all") else ""
            params.append(f"`{p['name']}` de {self.code(p['domain'])}{hidden}")
        line = f"- **{action['name']}**"
        if params:
            line += ": elige " + "; ".join(params)
        if "requires" in action:
            line += f". Solo si {self.code(action['requires'])}"
        doc = self.text(action.get("doc"))
        if doc:
            line += f". {doc}"
        self.add(line)
        if action.get("effects"):
            self.add(
                "", "  ```game", _indent(statements_text(self.ir, action["effects"]), "  "), "  ```"
            )
        for t in action.get("transitions", []):
            self.transition(t, "  ")
        self.add("")

    def transition(self, t: dict[str, Any], indent: str = "") -> None:
        target = "salir de la fase" if t["to"] == "$exit" else f"**{t['to']}**"
        line = f"{indent}- → {target}"
        if "when" in t:
            line += f" si {self.code(t['when'])}"
        if t.get("effects"):
            effects = statements_text(self.ir, t["effects"]).replace("\n", "; ")
            line += f", y antes: `{effects}`"
        self.add(line)

    def block(self, label: str, stmts: list[Any]) -> None:
        self.add(f"{label}:", "", "```game", statements_text(self.ir, stmts), "```", "")

    def functions(self) -> None:
        functions = self.ir.get("functions", [])
        if not functions:
            return
        self.add("## Definiciones", "", "```game")
        for i, f in enumerate(functions):
            if i:
                self.add("")
            self.add(function_text(self.ir, f))
        self.add("```", "")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())
