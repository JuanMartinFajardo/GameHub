// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Markdown sencillo a React, sin HTML: lo que escriben los autores (reglamentos, notas, informes
 * de balance) se muestra como texto, nunca se interpreta. Admite títulos, párrafos, listas,
 * tablas, citas, bloques de código (los de Mermaid se omiten: el diagrama va aparte), código en
 * línea, negrita, cursiva y enlaces (solo http, https y rutas del propio sitio).
 */

import type { ReactNode } from "react";

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "code"; lang: string; text: string }
  | { kind: "quote"; text: string }
  | { kind: "rule" };

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  const isTableRow = (line: string) => /^\s*\|.*\|\s*$/.test(line);
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = line.match(/^\s*(```|~~~)\s*([\w-]*)/);
    if (fence) {
      const close = fence[1] as string;
      const body: string[] = [];
      i++;
      while (i < lines.length && !(lines[i] ?? "").trim().startsWith(close))
        body.push(lines[i++] ?? "");
      i++;
      blocks.push({ kind: "code", lang: fence[2] ?? "", text: body.join("\n") });
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: (heading[1] as string).length,
        text: (heading[2] ?? "").trim(),
      });
      i++;
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
      i++;
      continue;
    }
    if (isTableRow(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] ?? "")) {
      const cells = (row: string) =>
        row
          .trim()
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((c) => c.trim());
      const header = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i] ?? "")) rows.push(cells(lines[i++] ?? ""));
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const item = line.match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
    if (item) {
      const ordered = /\d/.test(item[1] as string);
      const items: string[] = [];
      while (i < lines.length) {
        const m = (lines[i] ?? "").match(/^\s*([-*+]|\d+[.)])\s+(.*)$/);
        if (m) {
          items.push(m[2] ?? "");
          i++;
        } else if ((lines[i] ?? "").match(/^\s{2,}\S/) && items.length) {
          items[items.length - 1] += ` ${(lines[i] ?? "").trim()}`;
          i++;
        } else break;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    if (line.startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith(">"))
        body.push((lines[i++] ?? "").replace(/^>\s?/, ""));
      blocks.push({ kind: "quote", text: body.join(" ") });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? "").trim() &&
      !/^(#{1,6}\s|```|~~~|>|\s*([-*+]|\d+[.)])\s)/.test(lines[i] ?? "") &&
      !isTableRow(lines[i] ?? "")
    ) {
      para.push((lines[i++] ?? "").trim());
    }
    if (para.length === 0) {
      para.push(line.trim());
      i++;
    }
    blocks.push({ kind: "paragraph", text: para.join(" ") });
  }
  return blocks;
}

function safeHref(href: string): string | null {
  if (/^https?:\/\//i.test(href)) return href;
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  if (href.startsWith("#")) return href;
  return null;
}

/** El texto de un bloque con su formato en línea. */
export function inline(text: string, key = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern =
    /(`+)([^`]+?)\1|\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*|_([^_\s][^_]*)_|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let n = 0;
  for (const m of text.matchAll(pattern)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const k = `${key}-${n++}`;
    if (m[2] !== undefined) out.push(<code key={k}>{m[2]}</code>);
    else if (m[3] !== undefined) out.push(<strong key={k}>{inline(m[3], k)}</strong>);
    else if (m[4] !== undefined) out.push(<em key={k}>{inline(m[4], k)}</em>);
    else if (m[5] !== undefined) out.push(<em key={k}>{inline(m[5], k)}</em>);
    else if (m[6] !== undefined) {
      const href = safeHref(m[7] ?? "");
      out.push(
        href ? (
          <a key={k} href={href} rel="noopener noreferrer nofollow">
            {inline(m[6], k)}
          </a>
        ) : (
          m[6]
        ),
      );
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown(props: { source: string; skipMermaid?: boolean; className?: string }) {
  const blocks = parseMarkdown(props.source);
  return (
    <div className={props.className ?? "hub-markdown"}>
      {blocks.map((b, i) => {
        const k = `b${i}`;
        switch (b.kind) {
          case "heading": {
            const level = Math.min(6, b.level + 1);
            const Tag = `h${level}` as "h2";
            return <Tag key={k}>{inline(b.text, k)}</Tag>;
          }
          case "paragraph":
            return <p key={k}>{inline(b.text, k)}</p>;
          case "list": {
            const items = b.items.map((it, j) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: los bloques de un texto no se reordenan
              <li key={`${k}-${j}`}>{inline(it, `${k}-${j}`)}</li>
            ));
            return b.ordered ? <ol key={k}>{items}</ol> : <ul key={k}>{items}</ul>;
          }
          case "table":
            return (
              <div key={k} className="hub-table-wrap">
                <table>
                  <thead>
                    <tr>
                      {b.header.map((h, j) => (
                        // biome-ignore lint/suspicious/noArrayIndexKey: los bloques de un texto no se reordenan
                        <th key={`${k}-h${j}`}>{inline(h, `${k}-h${j}`)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((row, r) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: los bloques de un texto no se reordenan
                      <tr key={`${k}-r${r}`}>
                        {row.map((c, j) => (
                          // biome-ignore lint/suspicious/noArrayIndexKey: los bloques de un texto no se reordenan
                          <td key={`${k}-r${r}-${j}`}>{inline(c, `${k}-r${r}-${j}`)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "code":
            if (b.lang === "mermaid" && props.skipMermaid !== false) return null;
            return (
              <pre key={k} className="hub-code">
                <code>{b.text}</code>
              </pre>
            );
          case "quote":
            return <blockquote key={k}>{inline(b.text, k)}</blockquote>;
          case "rule":
            return <hr key={k} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
