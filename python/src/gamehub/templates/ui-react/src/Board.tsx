// SPDX-License-Identifier: Apache-2.0
/**
 * La interfaz de __TITLE__. Para empezar enseña el estado tal cual llega y un botón por cada
 * acción legal; cámbiala a tu gusto con los componentes de @gamehub/ui-kit (Grid, PlayingCard,
 * Hand, Die, Token, Clock…) o con lo que quieras.
 *
 * - `view.state` es el estado tal como lo ves (tipado en ./game.ts, generado de las reglas).
 * - `actions` son tus acciones legales si te toca (null si no); `act(acción)` juega una.
 * - `seat` es tu asiento; `players`, quién juega en cada uno.
 * - Al terminar la partida, la app enseña el resultado debajo de tu tablero.
 */

import type { GameUiProps } from "@gamehub/shell";
import { ActionBar, Badge, Button, Panel, PlayerBadge, seatColor } from "@gamehub/ui-kit";
import type { Action, State } from "./game";

function describe(action: Action): string {
  const args = Object.values(action.args as Record<string, unknown>).map((v) => JSON.stringify(v));
  return args.length > 0 ? `${action.name} (${args.join(", ")})` : action.name;
}

export function Board(props: GameUiProps<State, Action>) {
  const { view, actions, act, seat, players, busy } = props;
  const mine = actions !== null && !busy;
  return (
    <div className="__GAME_ID__-board">
      <Panel title="Jugadores">
        <ul className="__GAME_ID__-players">
          {players.map((p) => (
            <li key={p.seat}>
              <PlayerBadge
                name={p.name}
                color={seatColor(p.seat)}
                you={p.seat === seat}
                active={view.active.includes(p.seat)}
              />
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Estado" actions={<Badge>{view.node ?? "—"}</Badge>}>
        <dl className="__GAME_ID__-state">
          {Object.entries(view.state).map(([name, value]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>
                <code>{JSON.stringify(value)}</code>
              </dd>
            </div>
          ))}
        </dl>
      </Panel>
      {mine && (
        <ActionBar label="Te toca" sticky>
          {actions.map((a) => (
            <Button key={JSON.stringify(a)} onClick={() => act(a)}>
              {describe(a)}
            </Button>
          ))}
        </ActionBar>
      )}
    </div>
  );
}
