// SPDX-License-Identifier: Apache-2.0
/**
 * Ajedrez: el tablero de siempre (girado para quien lleva las negras). Se pulsa una pieza propia
 * y se marcan sus destinos legales; al llevar un peón a la última fila se elige la pieza. Se
 * resaltan la última jugada y el rey en jaque, y al lado van las piezas capturadas y las jugadas.
 */

import type { LoggedEvent } from "@gamehub/client";
import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { Button } from "@gamehub/ui-kit";
import { useEffect, useMemo, useState } from "react";
import type { Action, Cell, Kind, Piece, PlayAction, PromoteAction, State } from "./game";

const messages = defineMessages(
  {
    yourTurn: "Te toca",
    turnOf: "Juegan {name}",
    check: "¡Jaque!",
    checkmate: "Jaque mate: ganan {name}",
    youWon: "Jaque mate: ¡has ganado!",
    youLost: "Jaque mate: has perdido",
    stalemate: "Tablas: rey ahogado",
    draw: "Tablas",
    sending: "Enviando…",
    claimDraw: "Reclamar tablas",
    promoteTo: "Coronar en",
    cancel: "Cancelar",
    white: "blancas",
    black: "negras",
    moves: "Jugadas",
    captured: "Capturadas",
    square: "Casilla {name}",
    Queen: "Dama",
    Rook: "Torre",
    Bishop: "Alfil",
    Knight: "Caballo",
  },
  {
    yourTurn: "Your move",
    turnOf: "{name} to move",
    check: "Check!",
    checkmate: "Checkmate: {name} win",
    youWon: "Checkmate: you won!",
    youLost: "Checkmate: you lost",
    stalemate: "Draw by stalemate",
    draw: "Draw",
    sending: "Sending…",
    claimDraw: "Claim a draw",
    promoteTo: "Promote to",
    cancel: "Cancel",
    white: "White",
    black: "Black",
    moves: "Moves",
    captured: "Captured",
    square: "Square {name}",
    Queen: "Queen",
    Rook: "Rook",
    Bishop: "Bishop",
    Knight: "Knight",
  },
);

export const GLYPHS: Record<Piece, string> = {
  WhitePawn: "♙",
  WhiteKnight: "♘",
  WhiteBishop: "♗",
  WhiteRook: "♖",
  WhiteQueen: "♕",
  WhiteKing: "♔",
  BlackPawn: "♟",
  BlackKnight: "♞",
  BlackBishop: "♝",
  BlackRook: "♜",
  BlackQueen: "♛",
  BlackKing: "♚",
};

const PROMOTIONS = ["Queen", "Rook", "Bishop", "Knight"] as const satisfies readonly Kind[];

type Board = (Piece | null)[][];

/** «e4» para la casilla (fila 4, columna 4): la fila 0 es la octava. */
export function squareName([r, c]: Cell): string {
  return `${"abcdefgh"[c]}${8 - r}`;
}

const same = (a: Cell, b: Cell) => a[0] === b[0] && a[1] === b[1];
const isWhite = (p: Piece) => p.startsWith("White");

/** ¿Ataca alguna pieza del bando `white` la casilla `target`? (para marcar el jaque) */
export function attacked(board: Board, target: Cell, white: boolean): boolean {
  const at = (r: number, c: number) => (r >= 0 && r < 8 && c >= 0 && c < 8 ? board[r]?.[c] : null);
  const own = (p: Piece | null | undefined, kind: string) =>
    !!p && isWhite(p) === white && p.endsWith(kind);
  const [r, c] = target;
  const pawnRow = white ? r + 1 : r - 1;
  if (own(at(pawnRow, c - 1), "Pawn") || own(at(pawnRow, c + 1), "Pawn")) return true;
  const knight = [
    [-2, -1],
    [-2, 1],
    [-1, -2],
    [-1, 2],
    [1, -2],
    [1, 2],
    [2, -1],
    [2, 1],
  ];
  if (knight.some(([dr, dc]) => own(at(r + (dr ?? 0), c + (dc ?? 0)), "Knight"))) return true;
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      if (own(at(r + dr, c + dc), "King")) return true;
      const straight = dr === 0 || dc === 0;
      for (let k = 1; k < 8; k++) {
        const p = at(r + k * dr, c + k * dc);
        if (p === undefined) break;
        if (p === null) continue;
        if (own(p, "Queen") || own(p, straight ? "Rook" : "Bishop")) return true;
        break;
      }
    }
  }
  return false;
}

const START: Record<Piece, number> = {
  WhitePawn: 8,
  WhiteKnight: 2,
  WhiteBishop: 2,
  WhiteRook: 2,
  WhiteQueen: 1,
  WhiteKing: 1,
  BlackPawn: 8,
  BlackKnight: 2,
  BlackBishop: 2,
  BlackRook: 2,
  BlackQueen: 1,
  BlackKing: 1,
};

/** Las piezas que faltan en el tablero (las coronaciones pueden dar números negativos: no se
 * cuentan). */
export function capturedPieces(board: Board): Piece[] {
  const count = new Map<Piece, number>();
  for (const row of board) for (const p of row) if (p) count.set(p, (count.get(p) ?? 0) + 1);
  const out: Piece[] = [];
  for (const [piece, n] of Object.entries(START) as [Piece, number][]) {
    for (let i = count.get(piece) ?? 0; i < n; i++) out.push(piece);
  }
  return out;
}

interface Move {
  seat: number;
  from: Cell;
  to: Cell;
  into?: Kind;
}

/** Las jugadas de la partida, a partir del registro de eventos. */
export function readMoves(log: LoggedEvent[]): Move[] {
  const moves: Move[] = [];
  for (const { event } of log) {
    if (event.type !== "action" || (event.name !== "play" && event.name !== "promote")) continue;
    const args = event.args as { from: Cell; to: Cell; into?: Kind };
    moves.push({ seat: event.seat as number, from: args.from, to: args.to, into: args.into });
  }
  return moves;
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, log } = props;
  const state = view.state;
  const board = state.board;
  const [selected, setSelected] = useState<Cell | null>(null);
  const [promotion, setPromotion] = useState<{ from: Cell; to: Cell } | null>(null);
  // Cada turno empieza sin nada seleccionado.
  // biome-ignore lint/correctness/useExhaustiveDependencies: unas acciones nuevas = un turno nuevo.
  useEffect(() => {
    setSelected(null);
    setPromotion(null);
  }, [actions]);

  const mine = actions !== null && !busy;
  const moves = useMemo(
    () =>
      (mine ? actions : []).filter(
        (a): a is PlayAction | PromoteAction => a.name === "play" || a.name === "promote",
      ),
    [actions, mine],
  );
  const canClaim = mine && actions.some((a) => a.name === "claim_draw");
  const history = useMemo(() => readMoves(log), [log]);
  const last = history.at(-1);
  const flipped = seat === 1;
  const name = (s: number) =>
    players.find((p) => p.seat === s)?.name ?? (s === 0 ? t("white") : t("black"));
  const sideToMove = state.turn;
  const king = state.kings[sideToMove];
  const inCheck =
    view.status !== "terminal" || view.node === "Checkmate"
      ? king !== undefined && attacked(board, king, sideToMove === 1)
      : false;

  const targets = selected
    ? moves.filter((a) => same(a.args.from, selected)).map((a) => a.args.to)
    : [];
  const sources = new Set(moves.map((a) => squareName(a.args.from)));

  const onSquare = (cell: Cell) => {
    if (!mine) return;
    if (selected && targets.some((x) => same(x, cell))) {
      const promote = moves.filter(
        (a) => a.name === "promote" && same(a.args.from, selected) && same(a.args.to, cell),
      );
      if (promote.length > 0) {
        setPromotion({ from: selected, to: cell });
        return;
      }
      act({ name: "play", args: { from: selected, to: cell } });
      setSelected(null);
      return;
    }
    setSelected(sources.has(squareName(cell)) ? cell : null);
  };

  let status: string;
  if (view.status === "terminal") {
    if (view.node === "Checkmate") {
      const winner = 1 - sideToMove;
      status =
        seat === null
          ? t("checkmate", { name: name(winner) })
          : t(winner === seat ? "youWon" : "youLost");
    } else status = t(view.node === "Stalemate" ? "stalemate" : "draw");
  } else if (busy) status = t("sending");
  else if (mine) status = inCheck ? `${t("yourTurn")} · ${t("check")}` : t("yourTurn");
  else status = t("turnOf", { name: name(sideToMove) });

  const rows = flipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
  const cols = flipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
  const captured = capturedPieces(board);

  return (
    <div className="chess">
      <p className={`chess-status${mine ? " chess-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <div className="chess-layout">
        <div className="chess-board">
          {rows.map((r) => (
            <div key={r} className="chess-row">
              {cols.map((c) => {
                const cell: Cell = [r, c];
                const piece = board[r]?.[c] ?? null;
                const dark = (r + c) % 2 === 1;
                const isTarget = targets.some((x) => same(x, cell));
                const classes = [
                  "chess-square",
                  dark ? "chess-square--dark" : "chess-square--light",
                  selected && same(selected, cell) ? "chess-square--selected" : "",
                  isTarget ? (piece ? "chess-square--capture" : "chess-square--target") : "",
                  last && (same(last.from, cell) || same(last.to, cell))
                    ? "chess-square--last"
                    : "",
                  inCheck && king && same(king, cell) ? "chess-square--check" : "",
                  mine && sources.has(squareName(cell)) ? "chess-square--movable" : "",
                ].filter(Boolean);
                return (
                  <button
                    key={c}
                    type="button"
                    className={classes.join(" ")}
                    aria-label={`${t("square", { name: squareName(cell) })}${piece ? ` ${GLYPHS[piece]}` : ""}`}
                    onClick={() => onSquare(cell)}
                  >
                    {piece && (
                      <span
                        className={`chess-piece chess-piece--${isWhite(piece) ? "white" : "black"}`}
                      >
                        {GLYPHS[piece]}
                      </span>
                    )}
                    {c === cols[0] && <span className="chess-rank">{8 - r}</span>}
                    {r === rows[7] && <span className="chess-file">{"abcdefgh"[c]}</span>}
                  </button>
                );
              })}
            </div>
          ))}
          {promotion && (
            <div className="chess-promotion" role="dialog" aria-label={t("promoteTo")}>
              <span>{t("promoteTo")}</span>
              {PROMOTIONS.map((kind) => (
                <Button
                  key={kind}
                  onClick={() => {
                    act({ name: "promote", args: { ...promotion, into: kind } });
                    setPromotion(null);
                    setSelected(null);
                  }}
                  aria-label={t(kind)}
                >
                  {GLYPHS[`${sideToMove === 0 ? "White" : "Black"}${kind}` as Piece]}
                </Button>
              ))}
              <Button onClick={() => setPromotion(null)}>{t("cancel")}</Button>
            </div>
          )}
        </div>
        <aside className="chess-side">
          <ul className="chess-players">
            {players.map((p) => (
              <li
                key={p.seat}
                className={`chess-player${view.active.includes(p.seat) ? " chess-player--active" : ""}`}
              >
                <span className="chess-player__glyph">{p.seat === 0 ? "♔" : "♚"}</span>
                {p.name}
              </li>
            ))}
          </ul>
          {captured.length > 0 && (
            <section>
              <h3>{t("captured")}</h3>
              <p className="chess-captured">{captured.map((p) => GLYPHS[p]).join(" ")}</p>
            </section>
          )}
          {history.length > 0 && (
            <section>
              <h3>{t("moves")}</h3>
              <ol className="chess-moves">
                {pairs(history).map(([white, black], i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: la lista solo crece.
                  <li key={i}>
                    {describe(white)}
                    {black && ` ${describe(black)}`}
                  </li>
                ))}
              </ol>
            </section>
          )}
          {canClaim && (
            <Button onClick={() => act({ name: "claim_draw", args: {} })}>{t("claimDraw")}</Button>
          )}
        </aside>
      </div>
    </div>
  );
}

function describe(m: Move): string {
  const into = m.into ? `=${m.into[0] === "K" ? "N" : m.into[0]}` : "";
  return `${squareName(m.from)}–${squareName(m.to)}${into}`;
}

function pairs<T>(xs: T[]): [T, T | undefined][] {
  const out: [T, T | undefined][] = [];
  for (let i = 0; i < xs.length; i += 2) out.push([xs[i] as T, xs[i + 1]]);
  return out;
}
