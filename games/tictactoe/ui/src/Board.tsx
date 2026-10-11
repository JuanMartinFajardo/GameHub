// SPDX-License-Identifier: Apache-2.0
/**
 * Tres en raya: un tablero grande con las marcas dibujadas, la línea ganadora y, cuando te toca,
 * una vista previa de tu marca en las casillas libres.
 */

import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import type { Action, Cell, Mark, State } from "./game";

const messages = defineMessages(
  {
    yourTurn: "Te toca: pon tu {mark}",
    turnOf: "Turno de {name} ({mark})",
    won: "¡Has ganado!",
    lost: "Ha ganado {name}",
    wins: "Gana {name}",
    draw: "Tablas",
    cell: "Casilla {row}, {column}",
    empty: "vacía",
    sending: "Enviando…",
  },
  {
    yourTurn: "Your turn: place your {mark}",
    turnOf: "{name} to play ({mark})",
    won: "You won!",
    lost: "{name} won",
    wins: "{name} wins",
    draw: "Draw",
    cell: "Cell {row}, {column}",
    empty: "empty",
    sending: "Sending…",
  },
);

const MARKS: Record<Mark, string> = { X: "✕", O: "◯" };

const LINES: Cell[][] = [
  [
    [0, 0],
    [0, 1],
    [0, 2],
  ],
  [
    [1, 0],
    [1, 1],
    [1, 2],
  ],
  [
    [2, 0],
    [2, 1],
    [2, 2],
  ],
  [
    [0, 0],
    [1, 0],
    [2, 0],
  ],
  [
    [0, 1],
    [1, 1],
    [2, 1],
  ],
  [
    [0, 2],
    [1, 2],
    [2, 2],
  ],
  [
    [0, 0],
    [1, 1],
    [2, 2],
  ],
  [
    [0, 2],
    [1, 1],
    [2, 0],
  ],
];

/** La línea completa del tablero, si la hay. */
export function winningLine(board: (Mark | null)[][]): Cell[] | null {
  for (const line of LINES) {
    const marks = line.map(([r, c]) => board[r]?.[c] ?? null);
    if (marks[0] !== null && marks.every((m) => m === marks[0])) return line;
  }
  return null;
}

function MarkArt(props: { mark: Mark; ghost?: boolean }) {
  return (
    <svg
      viewBox="0 0 100 100"
      className={`ttt-mark ttt-mark--${props.mark}${props.ghost ? " ttt-mark--ghost" : ""}`}
      aria-hidden="true"
    >
      {props.mark === "X" ? (
        <>
          <line x1="22" y1="22" x2="78" y2="78" pathLength="1" />
          <line x1="78" y1="22" x2="22" y2="78" pathLength="1" />
        </>
      ) : (
        <circle cx="50" cy="50" r="30" pathLength="1" />
      )}
    </svg>
  );
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy } = props;
  const board = view.state.board;
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const markOf = (s: number): Mark => (s === 0 ? "X" : "O");
  const legal = new Set((busy ? [] : (actions ?? [])).map((a) => `${a.args.c[0]},${a.args.c[1]}`));
  const line = winningLine(board);
  const onLine = new Set((line ?? []).map(([r, c]) => `${r},${c}`));
  const turn = view.state.turn;

  let status: string;
  if (view.status === "terminal") {
    if (line === null) status = t("draw");
    else if (seat === null) status = t("wins", { name: name(turn) });
    else status = turn === seat ? t("won") : t("lost", { name: name(turn) });
  } else if (busy) {
    status = t("sending");
  } else if (actions !== null && seat !== null) {
    status = t("yourTurn", { mark: MARKS[markOf(seat)] });
  } else {
    status = t("turnOf", { name: name(turn), mark: MARKS[markOf(turn)] });
  }

  return (
    <div className="ttt">
      <p className={`ttt-status${actions && !busy ? " ttt-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <div className="ttt-board">
        {board.map((row, r) =>
          row.map((cell, c) => {
            const key = `${r},${c}`;
            const playable = legal.has(key);
            return (
              <button
                key={key}
                type="button"
                className={`ttt-cell${onLine.has(key) ? " ttt-cell--win" : ""}`}
                disabled={!playable}
                aria-label={`${t("cell", { row: r + 1, column: c + 1 })}: ${cell ? MARKS[cell] : t("empty")}`}
                onClick={() => act({ name: "place", args: { c: [r, c] } })}
              >
                {cell !== null && <MarkArt mark={cell} />}
                {cell === null && playable && seat !== null && (
                  <MarkArt mark={markOf(seat)} ghost />
                )}
              </button>
            );
          }),
        )}
      </div>
      <ul className="ttt-players">
        {players.map((p) => (
          <li
            key={p.seat}
            className={`ttt-player${view.active.includes(p.seat) ? " ttt-player--active" : ""}`}
          >
            <span className={`ttt-badge ttt-badge--${markOf(p.seat)}`}>
              {MARKS[markOf(p.seat)]}
            </span>
            {p.name}
            {p.seat === seat && " ·"}
          </li>
        ))}
      </ul>
    </div>
  );
}
