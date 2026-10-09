# Análisis del prototipo `structure.py`

`structure.py` (raíz del repo, 141 líneas, mayo 2026) es el primer intento de formalizar GameHub.
**Se conserva sin modificar** como referencia histórica. Este documento recoge qué intuiciones se
mantienen, qué problemas tiene y cómo se traduce cada concepto al nuevo modelo.

## 1. Intuiciones correctas que se conservan

| Concepto en `structure.py` | Idea de fondo (correcta) | Equivalente en GameHub |
|---|---|---|
| `GameState.global_variables` | El juego tiene un estado explícito | **Esquema de estado tipado** (`state { … }`) |
| `variable_permissions` (`'card': ['player1']`) | La información es parte de las reglas | **Políticas de visibilidad** (`@visible(owner)`, `@visible(all)`…) |
| `Player_Category` (blancas/negras, equipos) | Roles con permisos distintos | **Roles y equipos** (`roles`, `teams`) |
| `Flowchart`, `Node`, `current_node` | El juego es un diagrama de flujo | **Flow**: statechart jerárquico de nodos tipados |
| `Node.sequential` / `Action.multiplayer` | Turnos secuenciales vs. simultáneos | Tipos de nodo `decision`, `simultaneous`, `window` |
| `action_activation_functions` | Una acción solo es legal si se cumple una condición | **Guardas** de acción (`requires …`) |
| `players_activation_functions` | Quién puede actuar depende del estado | Expresiones `actor:` / `actors:` del nodo |
| `Action.action_parameters` | Las acciones llevan parámetros (qué carta…) | **Parámetros tipados con dominio** (`play(c: Card in hand[actor])`) |
| `modification_function` → `{'variables_to_update', 'permissions_to_update'}` | Los efectos son *datos* (un diff de estado) | **Efectos declarativos** (asignaciones, `move`, `reveal`…) |
| `Node.terminal` | Hay estados finales | Nodos `terminal` con **pagos** (payoffs) |
| `game_history` | Registro de lo ocurrido | **Log de eventos** + formato de **replay** |
| `get_action(player)` separado del motor | La entrada de los jugadores es externa | **Protocolo** (`act`) e interfaz `Agent` |

La intuición más valiosa: **los efectos devuelven un diccionario de cambios en lugar de mutar el
estado a mano**. Generalizada, es exactamente lo que permite que las reglas sean datos analizables.

## 2. Problemas detectados

### Errores que impiden ejecutarlo
1. **L44** `GameState('game_state')`: `__new__(cls)` no acepta argumentos → `TypeError` al importar.
2. **L99–106** `apply_action(self, actions, players, parameters)` usa `action` (no definido);
   devuelve tras el primer jugador e ignora al resto; nunca usa `parameters`.
3. **L95–97 / L101** las funciones de activación por defecto son `None`; llamarlas da `TypeError`.
   Además la firma documentada `(state, player, extra)` no coincide con la llamada `(state, player)`.
4. **L52–57** `Player.category`: `categories = []` se reinicia *dentro* del bucle (solo devuelve
   la última categoría) y lanza `UnboundLocalError` si no hay categorías.
5. **L40–41** `update_history` hace `deepcopy` y descarta el resultado; `game_history` nunca se llena.
6. **L131–141** `run_game` está incompleto; la rama no secuencial pide y aplica acciones jugador a
   jugador (no es simultánea de verdad) y falta la rama secuencial.

### Problemas de diseño (los importantes)
1. **Singleton de estado.** Solo puede existir *una* partida por proceso. Imposible simular
   ramas (minimax, MCTS), entrenar en paralelo (RL) o servir varias salas. → **Estados
   inmutables**: `s' = apply(s, a)`; cualquier número de estados conviven.
2. **Reglas como funciones Python arbitrarias.** No se pueden serializar, portar a C++/navegador,
   ejecutar con seguridad en un servidor ni analizar. → **Lenguaje de expresiones puro y tipado**.
3. **`Action.end` fija el destino.** La transición no puede depender del estado ("si alguien gana,
   ir a Fin; si no, siguiente turno"). → **Transiciones con guardas** evaluadas en orden.
4. **Visibilidad a nivel de variable completa.** No permite "el número de cartas de tu mano es
   público, pero cuáles son no", ni variables por jugador, ni cartas que cambian de zona, ni
   revelar en un momento dado. → **Visibilidad por ubicación** (variable, zona, componente,
   evento) y **dependiente del estado**.
5. **Faltan conceptos esenciales:** azar (jugador *naturaleza* con distribuciones), pagos y
   resultados, parámetros/variantes, número de jugadores variable, tiempo (relojes, plazos),
   ventanas de reacción (¡Mentiroso!), reglas que dependen del historial (triple repetición).
6. **E/S mezclada con el motor** (`get_action` dentro de `run_game`). → El motor es una función
   pura; el bucle de partida vive en un *driver* (servidor, CLI, simulador, entrenador).
7. **Concepto de "jugador" mezclado con "asiento".** → Se distinguen **asientos** (posición en
   las reglas: 0..n-1) de **participantes** (humano, bot, espectador que ocupa un asiento).

## 3. El mismo espíritu, en el nuevo modelo

Lo que `structure.py` intentaba expresar, escrito con la API Python prevista (que genera IR, no
ejecuta lambdas):

```python
from gamehub.build import Game, Seat, Enum, Grid, opt

g = Game("TicTacToe", players=2)
Mark = g.enum("Mark", ["X", "O"])
board = g.state("board", Grid(3, 3, opt(Mark)), init=None)          # público por defecto
turn  = g.state("turn", Seat, init=0)

move = g.decision("Move", actor=turn)
c = move.action("place", c=board.cells()).requires(board[c].is_none())
c.effect(board[c].set(Mark.of_seat(turn)))
move.to("Win",  when=board.has_line(Mark.of_seat(turn), length=3))
move.to("Draw", when=board.is_full())
move.to("Move", effect=turn.set(turn.next()))

g.terminal("Win",  payoff=g.zero_sum(winner=turn))
g.terminal("Draw", payoff=0)
g.start("Move")

ir = g.build()        # → GameIR (JSON canónico), idéntica a la que produce el texto .game
```

Ver [Modelo formal](modelo-formal.md) y [Lenguaje `.game`](lenguaje-game.md).
