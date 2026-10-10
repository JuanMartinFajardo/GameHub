// SPDX-License-Identifier: Apache-2.0
/** Galería del kit de componentes (/kit): para ver de un vistazo cómo queda cada pieza. */

import {
  ActionBar,
  Badge,
  Button,
  Chips,
  Clock,
  Counter,
  Deck,
  Dice,
  Die,
  GraphBoard,
  Grid,
  Hand,
  Panel,
  Pile,
  PlayerBadge,
  PlayingCard,
  Scoreboard,
  seatColor,
  standardSuit,
  Token,
  Track,
} from "@gamehub/ui-kit";
import { useState } from "react";

const SUITS = ["Hearts", "Spades", "Diamonds", "Clubs"];
const RANKS = ["A", "7", "10", "Q", "K"];

export function Kit() {
  const [selected, setSelected] = useState<number[]>([1]);
  const [board, setBoard] = useState<(string | null)[][]>([
    [null, "X", null],
    [null, "O", null],
    [null, null, null],
  ]);
  const toggle = (i: number) =>
    setSelected((s) => (s.includes(i) ? s.filter((x) => x !== i) : [...s, i]));
  return (
    <div className="gh-shell-page">
      <h1>Kit de componentes</h1>
      <Panel title="Cartas">
        <div className="gh-shell-row">
          {SUITS.map((s, i) => (
            <PlayingCard key={s} rank={RANKS[i] ?? "A"} suit={standardSuit(s)} />
          ))}
          <PlayingCard faceDown />
          <PlayingCard rank="K" size="sm" />
          <PlayingCard rank="J" suit={standardSuit("Oros")} size="lg" />
        </div>
      </Panel>
      <Panel title="Mano (abanico, con selección)">
        <Hand label="Mi mano">
          {RANKS.map((r, i) => (
            <PlayingCard
              key={r}
              rank={r}
              suit={standardSuit(SUITS[i % 4] ?? "Hearts")}
              selected={selected.includes(i)}
              target={!selected.includes(i)}
              onClick={() => toggle(i)}
            />
          ))}
        </Hand>
        <Hand label="Mano ajena" hidden={6} />
      </Panel>
      <div className="gh-shell-columns">
        <Panel title="Montón y mazo">
          <div className="gh-shell-row">
            <Pile
              count={12}
              label="Montón"
              top={<PlayingCard rank="9" suit={standardSuit("Clubs")} />}
            />
            <Deck count={40} label="Mazo" />
            <Deck count={0} label="Vacío" />
          </div>
        </Panel>
        <Panel title="Dados y fichas">
          <div className="gh-shell-form">
            <Dice values={[1, 2, 3, 4, 5, 6]} />
            <div className="gh-shell-row">
              <Die value={null} />
              <Die value={4} highlight />
              <Die value={12} size="lg" />
            </div>
            <div className="gh-shell-row">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((s) => (
                <Token key={s} color={seatColor(s)} />
              ))}
              <Token glyph color={seatColor(0)}>
                ✕
              </Token>
              <Token glyph color={seatColor(1)}>
                ◯
              </Token>
            </div>
          </div>
        </Panel>
      </div>
      <div className="gh-shell-columns">
        <Panel title="Rejilla (pulsa una casilla libre)">
          <Grid
            rows={3}
            columns={3}
            label="Tres en raya"
            isTarget={(r, c) => board[r]?.[c] === null}
            onSelect={(r, c) =>
              setBoard((b) => b.map((row, i) => row.map((x, j) => (i === r && j === c ? "X" : x))))
            }
            renderCell={(r, c) => {
              const v = board[r]?.[c];
              return v ? (
                <Token glyph color={v === "X" ? seatColor(0) : seatColor(1)}>
                  {v === "X" ? "✕" : "◯"}
                </Token>
              ) : null;
            }}
          />
        </Panel>
        <Panel title="Rejilla por columnas">
          <Grid
            rows={6}
            columns={7}
            mode="column"
            label="Conecta 4"
            cellSize="40px"
            isTarget={() => true}
            onSelect={() => {}}
            renderCell={(r, c) =>
              r === 5 && c === 3 ? (
                <Token size="fill" color="#e53935" />
              ) : r === 5 && c === 4 ? (
                <Token size="fill" color="#fdd835" />
              ) : null
            }
          />
        </Panel>
      </div>
      <div className="gh-shell-columns">
        <Panel title="Recorrido">
          <Track
            spaces={12}
            tokens={[
              { at: 2, color: seatColor(0), label: "Ana" },
              { at: 7, color: seatColor(1), label: "Luis" },
              { at: 7, color: seatColor(2), label: "Eva" },
            ]}
            isTarget={(i) => i === 4}
            onSelect={() => {}}
          />
        </Panel>
        <Panel title="Grafo">
          <GraphBoard
            width={320}
            height={180}
            nodes={[
              { id: "a", x: 40, y: 90, label: "A" },
              { id: "b", x: 160, y: 40, label: "B" },
              { id: "c", x: 160, y: 140, label: "C" },
              { id: "d", x: 280, y: 90, label: "D" },
            ]}
            edges={[
              ["a", "b"],
              ["a", "c"],
              ["b", "d"],
              ["c", "d"],
            ]}
            tokens={[{ at: "b", color: seatColor(0) }]}
            isTarget={(id) => id === "d"}
            onSelect={() => {}}
          />
        </Panel>
      </div>
      <div className="gh-shell-columns">
        <Panel title="Jugadores, marcador y relojes">
          <div className="gh-shell-form">
            <PlayerBadge name="Ana" color={seatColor(0)} active you />
            <PlayerBadge name="Bot random" color={seatColor(1)} bot />
            <PlayerBadge name="Luis" color={seatColor(2)} away />
            <Scoreboard
              columns={["Jugador", "Puesto", "Pago"]}
              rows={[
                { name: "Ana", color: seatColor(0), values: ["#1", 2], highlight: true },
                { name: "Luis", color: seatColor(1), values: ["#2", -2] },
              ]}
            />
            <div className="gh-shell-row">
              <Clock ms={95_000} running />
              <Clock ms={8_000} running />
              <Clock ms={300_000} />
              <Counter value={7} label="Dados" />
              <Chips amount={25} label="Fichas" />
            </div>
          </div>
        </Panel>
        <Panel title="Botones e insignias">
          <div className="gh-shell-form">
            <div className="gh-shell-row">
              <Button variant="primary">Principal</Button>
              <Button>Secundario</Button>
              <Button variant="ghost">Sutil</Button>
              <Button variant="danger">Peligro</Button>
              <Button disabled>Desactivado</Button>
            </div>
            <div className="gh-shell-row">
              <Badge>neutra</Badge>
              <Badge tone="accent">te toca</Badge>
              <Badge tone="success">listo</Badge>
              <Badge tone="warning">reconectando</Badge>
              <Badge tone="danger">rechazada</Badge>
            </div>
          </div>
        </Panel>
      </div>
      <ActionBar label="Barra de acciones">
        <Button variant="primary">Pasar</Button>
        <Button>Apostar…</Button>
        <Button variant="ghost">Cancelar</Button>
      </ActionBar>
    </div>
  );
}
