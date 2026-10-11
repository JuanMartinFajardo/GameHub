// SPDX-License-Identifier: Apache-2.0
/**
 * Conecta 4: el tablero azul de siempre. Las fichas caen hasta su sitio, la columna se resalta al
 * pasar por encima (con la ficha que caería) y, al final, se marcan las fichas de la línea.
 */

import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { type CSSProperties, useState } from "react";
import type { Action, Disc, State } from "./game";

const messages = defineMessages(
  {
    yourTurn: "Te toca: suelta una ficha",
    turnOf: "Turno de {name}",
    won: "¡Has ganado!",
    lost: "Ha ganado {name}",
    wins: "Gana {name}",
    draw: "Tablas",
    column: "Columna {n}",
    sending: "Enviando…",
    red: "rojas",
    yellow: "amarillas",
  },
  {
    yourTurn: "Your turn: drop a disc",
    turnOf: "{name} to play",
    won: "You won!",
    lost: "{name} won",
    wins: "{name} wins",
    draw: "Draw",
    column: "Column {n}",
    sending: "Sending…",
    red: "red",
    yellow: "yellow",
  },
);

const DISCS: Disc[] = ["Red", "Yellow"];

/** Las casillas de la primera línea de `connect` fichas iguales, si la hay. */
export function winningCells(board: (Disc | null)[][], connect: number): Set<string> {
  const rows = board.length;
  const columns = board[0]?.length ?? 0;
  const steps: [number, number][] = [
    [0, 1],
    [1, 0],
    [1, 1],
    [1, -1],
  ];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const disc = board[r]?.[c];
      if (!disc) continue;
      for (const [dr, dc] of steps) {
        const cells: string[] = [];
        for (let k = 0; k < connect; k++) {
          const rr = r + dr * k;
          const cc = c + dc * k;
          if (board[rr]?.[cc] !== disc) break;
          cells.push(`${rr},${cc}`);
        }
        if (cells.length === connect) return new Set(cells);
      }
    }
  }
  return new Set();
}

/** La fila donde se queda una ficha soltada en la columna `c` (o -1 si está llena). */
export function landingRow(board: (Disc | null)[][], c: number): number {
  for (let r = board.length - 1; r >= 0; r--) if (board[r]?.[c] === null) return r;
  return -1;
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, params } = props;
  const [hover, setHover] = useState<number | null>(null);
  const board = view.state.board;
  const rows = board.length;
  const columns = board[0]?.length ?? 0;
  const connect = typeof params.connect === "number" ? params.connect : 4;
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const playable = new Set((busy ? [] : (actions ?? [])).map((a) => a.args.c));
  const mine = seat !== null ? DISCS[seat] : undefined;
  const line = view.status === "terminal" ? winningCells(board, connect) : new Set<string>();
  const turn = view.state.turn;

  let status: string;
  if (view.status === "terminal") {
    if (line.size === 0) status = t("draw");
    else if (seat === null) status = t("wins", { name: name(turn) });
    else status = turn === seat ? t("won") : t("lost", { name: name(turn) });
  } else if (busy) status = t("sending");
  else if (actions !== null && seat !== null) status = t("yourTurn");
  else status = t("turnOf", { name: name(turn) });

  const preview = hover !== null && playable.has(hover) ? landingRow(board, hover) : -1;
  const style = { "--c4-columns": columns, "--c4-rows": rows } as CSSProperties;
  return (
    <div className="c4">
      <p className={`c4-status${actions && !busy ? " c4-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <ul className="c4-players">
        {players.map((p) => (
          <li
            key={p.seat}
            className={`c4-player${view.active.includes(p.seat) ? " c4-player--active" : ""}`}
          >
            <span className={`c4-chip c4-disc--${DISCS[p.seat] ?? "Red"}`} />
            {p.name}
          </li>
        ))}
      </ul>
      <div className="c4-board" style={style}>
        {Array.from({ length: columns }, (_, c) => (
          <button
            // biome-ignore lint/suspicious/noArrayIndexKey: columnas fijas del tablero.
            key={c}
            type="button"
            className={`c4-column${hover === c && playable.has(c) ? " c4-column--hover" : ""}`}
            disabled={!playable.has(c)}
            aria-label={t("column", { n: c + 1 })}
            onMouseEnter={() => setHover(c)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(c)}
            onBlur={() => setHover(null)}
            onClick={() => act({ name: "drop", args: { c } })}
          >
            {Array.from({ length: rows }, (_, r) => {
              const disc = board[r]?.[c] ?? null;
              const ghost = disc === null && r === preview && mine !== undefined;
              return (
                // biome-ignore lint/suspicious/noArrayIndexKey: casillas fijas del tablero.
                <span key={r} className="c4-hole">
                  {disc !== null && (
                    <span
                      className={`c4-disc c4-disc--${disc}${line.has(`${r},${c}`) ? " c4-disc--win" : ""}`}
                      style={{ "--c4-row": r } as CSSProperties}
                    />
                  )}
                  {ghost && <span className={`c4-disc c4-disc--${mine} c4-disc--ghost`} />}
                </span>
              );
            })}
          </button>
        ))}
      </div>
    </div>
  );
}
