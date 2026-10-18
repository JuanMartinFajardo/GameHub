// SPDX-License-Identifier: AGPL-3.0-or-later
/** Un parche unificado de git, por archivo (sin las cabeceras `diff --git`/`index`). */
export function splitPatch(patch: string): { name: string; lines: string[] }[] {
  const out: { name: string; lines: string[] }[] = [];
  let current: { name: string; lines: string[] } | null = null;
  for (const line of patch.split("\n")) {
    if (line.startsWith("diff --git ")) {
      const m = line.match(/ b\/(.*)$/);
      current = { name: m?.[1] ?? line.slice(11), lines: [] };
      out.push(current);
    } else if (
      current &&
      !/^(index |--- |\+\+\+ |new file mode|deleted file mode|similarity index|rename (from|to) )/.test(
        line,
      )
    ) {
      current.lines.push(line);
    }
  }
  for (const f of out) {
    while (f.lines.length && f.lines[f.lines.length - 1] === "") f.lines.pop();
  }
  return out;
}
