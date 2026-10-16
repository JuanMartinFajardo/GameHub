// SPDX-License-Identifier: Apache-2.0
/**
 * Parchís: el tablero en cruz con sus 68 casillas, los seguros, las salidas, los pasillos, las
 * casas y la meta. Las fichas que se pueden mover con la tirada (o con el premio) se resaltan y se
 * mueven pulsándolas; al lado, el dado, el premio y quién juega.
 */

import { defineMessages, useMessages } from "@gamehub/i18n";
import type { GameUiProps } from "@gamehub/shell";
import { Die } from "@gamehub/ui-kit";
import type { Action, State } from "./game";
import {
  COLORS,
  colorOf,
  corridorPoint,
  exitSquare,
  isSafe,
  type Point,
  pawnPoint,
  RING,
  SIZE,
} from "./geometry";

const messages = defineMessages(
  {
    yourTurn: "Te toca: mueve una ficha {n}",
    yourBonus: "¡Premio! Cuenta {n} con una ficha",
    turnOf: "Le toca a {name}",
    sending: "Enviando…",
    won: "¡Gana {name}!",
    wonPair: "¡Ganan {a} y {b}!",
    die: "Dado",
    bonus: "Premio: {n}",
    sixes: "Seises seguidos: {n}",
    pawn: "Ficha {k} de {name}",
    atHome: "en casa",
    atGoal: "en la meta",
    colors: "amarillo|azul|rojo|verde",
  },
  {
    yourTurn: "Your turn: move a pawn {n}",
    yourBonus: "Bonus! Move a pawn {n}",
    turnOf: "{name} to play",
    sending: "Sending…",
    won: "{name} wins!",
    wonPair: "{a} and {b} win!",
    die: "Die",
    bonus: "Bonus: {n}",
    sixes: "Sixes in a row: {n}",
    pawn: "Pawn {k} of {name}",
    atHome: "at home",
    atGoal: "home safe",
    colors: "yellow|blue|red|green",
  },
);

const CELL = 28;

function center([x, y]: Point): [number, number] {
  return [(x + 0.5) * CELL, (y + 0.5) * CELL];
}

/** Lo que cuenta la tirada (un seis vale siete si no queda ninguna ficha en casa). */
export function steps(die: number, pawns: number[]): number {
  return die === 6 && pawns.every((p) => p >= 0) ? 7 : die;
}

function Squares() {
  return (
    <g className="parchis-squares">
      {RING.map((p, i) => {
        const q = i + 1;
        const exitOf = [0, 1, 2, 3].find((c) => exitSquare(c) === q);
        const [x, y] = [p[0] * CELL, p[1] * CELL];
        return (
          <g key={q}>
            <rect
              x={x}
              y={y}
              width={CELL}
              height={CELL}
              className="parchis-square"
              fill={exitOf !== undefined ? COLORS[exitOf] : "var(--parchis-square)"}
            />
            {isSafe(q) && (
              <circle
                cx={x + CELL / 2}
                cy={y + CELL / 2}
                r={CELL * 0.32}
                className="parchis-safe"
              />
            )}
            <text x={x + 2} y={y + 8} className="parchis-number">
              {q}
            </text>
          </g>
        );
      })}
      {[0, 1, 2, 3].map((c) =>
        Array.from({ length: 7 }, (_, j) => {
          const [x, y] = corridorPoint(c, j);
          return (
            <rect
              // biome-ignore lint/suspicious/noArrayIndexKey: casillas fijas del pasillo.
              key={`${c}-${j}`}
              x={x * CELL}
              y={y * CELL}
              width={CELL}
              height={CELL}
              className="parchis-square"
              fill={COLORS[c]}
              opacity={0.75}
            />
          );
        }),
      )}
    </g>
  );
}

function Homes() {
  const corners: [number, Point][] = [
    [0, [11, 11]],
    [1, [11, 0]],
    [2, [0, 0]],
    [3, [0, 11]],
  ];
  return (
    <g>
      {corners.map(([c, [x, y]]) => (
        <rect
          key={c}
          x={x * CELL + 4}
          y={y * CELL + 4}
          width={8 * CELL - 8}
          height={8 * CELL - 8}
          rx={18}
          fill={COLORS[c]}
          className="parchis-home"
        />
      ))}
      {/* La meta: un triángulo de cada color hacia su pasillo. */}
      {[0, 1, 2, 3].map((c) => {
        const mid = 9.5 * CELL;
        const lo = 8 * CELL;
        const hi = 11 * CELL;
        const tips: Record<number, string> = {
          0: `${lo},${hi} ${hi},${hi} ${mid},${mid}`,
          1: `${hi},${lo} ${hi},${hi} ${mid},${mid}`,
          2: `${lo},${lo} ${hi},${lo} ${mid},${mid}`,
          3: `${lo},${lo} ${lo},${hi} ${mid},${mid}`,
        };
        return <polygon key={c} points={tips[c]} fill={COLORS[c]} className="parchis-goal" />;
      })}
    </g>
  );
}

export function Board(props: GameUiProps<State, Action>) {
  const t = useMessages(messages);
  const { view, actions, act, seat, players, busy, params } = props;
  const state = view.state;
  const n = state.pos.length;
  const pairs = params.pairs === true;
  const name = (s: number) => players.find((p) => p.seat === s)?.name ?? `#${s + 1}`;
  const colorNames = t("colors").split("|");
  const mine = actions !== null && !busy;
  const movable = new Set((mine ? actions : []).map((a) => a.args.k));
  const bonusMove = mine && actions.some((a) => a.name === "count_bonus");
  // Por parejas, quien ya ha terminado mueve las fichas de su compañero.
  const finished = (s: number) => (state.pos[s] ?? []).every((p) => p === 71);
  const mover = (s: number) => (pairs && finished(s) ? (s + 2) % 4 : s);
  const owner = seat === null ? null : mover(seat);

  let status: string;
  if (view.status === "terminal") {
    status = pairs
      ? t("wonPair", { a: name(state.winner), b: name((state.winner + 2) % 4) })
      : t("won", { name: name(state.winner) });
  } else if (busy) status = t("sending");
  else if (bonusMove) status = t("yourBonus", { n: state.bonus });
  else if (mine) status = t("yourTurn", { n: steps(state.die, state.pos[owner ?? 0] ?? []) });
  else status = t("turnOf", { name: name(state.turn) });

  // Varias fichas en la misma casilla se separan un poco.
  const seen = new Map<string, number>();
  const pawns = state.pos.flatMap((list, s) =>
    list.map((i, k) => {
      const color = colorOf(s, n);
      const point = pawnPoint(color, i, k);
      const spot = i < 0 || i === 71 ? `${s}-${i}-${k}` : point.join(",");
      const index = seen.get(spot) ?? 0;
      seen.set(spot, index + 1);
      return { s, k, i, color, point, offset: index };
    }),
  );

  return (
    <div className="parchis">
      <p className={`parchis-status${mine ? " parchis-status--mine" : ""}`} aria-live="polite">
        {status}
      </p>
      <div className="parchis-layout">
        <svg
          className="parchis-board"
          viewBox={`0 0 ${SIZE * CELL} ${SIZE * CELL}`}
          role="img"
          aria-label="Parchís"
        >
          <rect width={SIZE * CELL} height={SIZE * CELL} rx={12} className="parchis-bg" />
          <Homes />
          <Squares />
          {pawns.map(({ s, k, i, color, point, offset }) => {
            const [cx, cy] = center(point);
            const can = owner === s && movable.has(k);
            const where = i < 0 ? t("atHome") : i === 71 ? t("atGoal") : `${i}`;
            return (
              // biome-ignore lint/a11y/useSemanticElements: una ficha de SVG que se pulsa.
              <g
                key={`${s}-${k}`}
                role="button"
                tabIndex={can ? 0 : -1}
                aria-label={`${t("pawn", { k: k + 1, name: name(s) })} (${where})`}
                aria-disabled={!can}
                className={`parchis-pawn${can ? " parchis-pawn--movable" : ""}`}
                transform={`translate(${cx + offset * 7 - (offset ? 3.5 : 0)}, ${cy - offset * 5})`}
                onClick={() =>
                  can && act({ name: bonusMove ? "count_bonus" : "advance", args: { k } })
                }
                onKeyDown={(e) => {
                  if (can && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    act({ name: bonusMove ? "count_bonus" : "advance", args: { k } });
                  }
                }}
              >
                <circle r={CELL * 0.36} fill={COLORS[color]} className="parchis-pawn__body" />
                <text className="parchis-pawn__label" dy="0.35em">
                  {k + 1}
                </text>
              </g>
            );
          })}
        </svg>
        <aside className="parchis-side">
          <div className="parchis-die">
            <Die value={state.die} size="lg" label={t("die")} />
            {state.bonus > 0 && <strong>{t("bonus", { n: state.bonus })}</strong>}
            {state.sixes > 0 && <span>{t("sixes", { n: state.sixes })}</span>}
          </div>
          <ul className="parchis-players">
            {state.pos.map((list, s) => (
              <li
                // biome-ignore lint/suspicious/noArrayIndexKey: un elemento por asiento.
                key={s}
                className={`parchis-player${view.active.includes(s) ? " parchis-player--active" : ""}`}
              >
                <span className="parchis-chip" style={{ background: COLORS[colorOf(s, n)] }} />
                <strong>{name(s)}</strong>
                <span className="parchis-muted">{colorNames[colorOf(s, n)]}</span>
                <span className="parchis-muted">{list.filter((p) => p === 71).length}/4</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
