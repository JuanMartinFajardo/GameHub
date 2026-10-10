// SPDX-License-Identifier: Apache-2.0
// La UI propia de Dudo: la app la usa en vez de la genérica (con un botón para cambiar).
import "./styles.css";
import { defineGameUi } from "@gamehub/shell";
import { Board } from "./Board";
import { type Action, GAME_ID, type State } from "./game";

export default defineGameUi<State, Action>({ game: GAME_ID, component: Board });
