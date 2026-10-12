// SPDX-License-Identifier: Apache-2.0
/**
 * El diseñador de componentes genera declaraciones de Nomos (una baraja, un tablero, unos
 * dados) que se insertan en el juego con la operación `insertSource`. Aquí está el texto que
 * genera cada uno (sin React, para probarlo).
 */

export interface Generated {
  /** Declaraciones del juego (lo que va dentro de `game X { … }`). */
  items: string;
  /** Lo que hay que importar, si hace falta. */
  imports?: { path: string[]; names: string[] };
}

export function identifiers(text: string): string[] {
  return text
    .split(/[,\s]+/)
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => v.replace(/[^A-Za-z0-9_]/g, ""))
    .filter((v) => /^[A-Za-z_]/.test(v));
}

const camel = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/** Una baraja: palos × valores (o la francesa de la biblioteca estándar). */
export function deckSource(options: {
  french: boolean;
  suits: string;
  ranks: string;
  card: string;
}): Generated {
  if (options.french) {
    return {
      imports: {
        path: ["std", "cards"],
        names: ["Card", "Suit", "Rank", "french52", "rank_value"],
      },
      items: [
        "state {",
        "  @visible(none)",
        "  deck: Zone<Card> = french52()",
        "}",
        "ui {",
        "  deck: deck",
        "  Card: card(rank: rank, suit: suit)",
        "}",
      ].join("\n"),
    };
  }
  const card = camel(identifiers(options.card)[0] ?? "Card");
  const suits = identifiers(options.suits).map(camel);
  const ranks = identifiers(options.ranks).map(camel);
  const suit = `${card}Suit`;
  const rank = `${card}Rank`;
  const deck = `${lower(card)}Deck`;
  return {
    items: [
      `enum ${suit} { ${suits.join(", ")} }`,
      `enum ${rank} { ${ranks.join(", ")} }`,
      `struct ${card} { suit: ${suit}, rank: ${rank} }`,
      `fn ${deck}() -> List<${card}> = [${card} { suit: s, rank: r } for s in ${suit}.values for r in ${rank}.values]`,
      "state {",
      "  @visible(none)",
      `  deck: Zone<${card}> = ${deck}()`,
      "}",
      "ui {",
      "  deck: deck",
      `  ${card}: card(rank: rank, suit: suit)`,
      "}",
    ].join("\n"),
  };
}

/** Un tablero de rejilla. */
export function gridSource(options: { width: number; height: number; cell: string }): Generated {
  const cell = options.cell.trim() || "Int";
  const init = cell.endsWith("?") ? " = none" : "";
  return {
    items: [
      "state {",
      `  board: Grid[${options.width}, ${options.height}] of ${cell}${init}`,
      "}",
      "ui {",
      "  board: grid",
      "}",
    ].join("\n"),
  };
}

/** Un tablero de grafo: casillas (un enumerado) y sus conexiones (`A-B`, sin dirección). */
export function graphBoardSource(options: { squares: string; edges: string }): Generated {
  const squares = identifiers(options.squares).map(camel);
  const pairs = options.edges
    .split(/[,;\n]+/)
    .map((e) => e.split(/[-–>]+/).map((s) => camel(s.trim())))
    .filter(
      (p): p is [string, string] =>
        p.length === 2 && squares.includes(p[0] ?? "") && squares.includes(p[1] ?? ""),
    );
  const list = pairs.map(([a, b]) => `(${a}, ${b})`).join(", ");
  return {
    items: [
      `enum Square { ${squares.join(", ")} }`,
      `/// Las conexiones del tablero (en los dos sentidos).`,
      `fn board_edges() -> List<(Square, Square)> = [${list}]`,
      "/// Las casillas conectadas con `s`.",
      "fn adjacent_squares(s: Square) -> List<Square> =",
      "  [e[1] for e in board_edges() if e[0] == s] + [e[0] for e in board_edges() if e[1] == s]",
    ].join("\n"),
  };
}

/**
 * Unos dados: el estado y un nodo de azar que los tira y sigue a `next` (otro nodo del juego; sin
 * él, vuelve a tirar, y habrá que cambiar la flecha en el diagrama).
 */
export function diceSource(options: { count: number; faces: number; next?: string }): Generated {
  const zeros = Array.from({ length: options.count }, () => "1").join(", ");
  return {
    items: [
      "state {",
      `  dice: List<Int> = [${zeros}]`,
      "}",
      "flow {",
      "  chance RollDice {",
      `    for i in 0..<${options.count} {`,
      `      dice[i] = roll(${options.faces})`,
      "    }",
      `    -> ${options.next || "RollDice"}`,
      "  }",
      "}",
      "ui {",
      "  dice: dice",
      "}",
    ].join("\n"),
  };
}
