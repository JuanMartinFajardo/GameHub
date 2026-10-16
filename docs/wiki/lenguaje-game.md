# Nomos — el lenguaje `.game` (referencia v0.1)

> Estado: **implementado** (Fase 2). Compilador en [`python/src/gamehub/lang`](../../python/src/gamehub/lang);
> el texto se traduce a [GameIR](ir.md), que ejecuta el [motor](motor.md). La semántica de fondo
> está en el [modelo formal](modelo-formal.md). Esta página es la referencia del lenguaje tal
> como funciona hoy; al final se resumen las diferencias con el RFC de la Fase 0.

## 1. Objetivos de diseño

- **Legible por humanos** y **diffeable**: un cambio de regla es un diff pequeño (y
  `gamehub diff` lo explica por elementos).
- **Correspondencia 1:1 con el diagrama**: cada nodo es una caja y cada `->` una flecha con su
  condición (`gamehub viz` dibuja exactamente eso).
- **Expresiones puras, tipadas y totales** (sin recursión ni bucles infinitos); los efectos, solo
  en bloques de efectos. El azar, solo en nodos `chance` y en la preparación.
- Sintaxis con llaves, palabras clave en inglés y expresiones al estilo de Python (`and`, `or`,
  `not`, `in`, `a if c else b`); los textos que ve el jugador, traducibles.

## 2. Un vistazo

```game
game TicTacToe {
  meta {
    id: "tictactoe"
    version: "1.0.0"
    title: { es: "Tres en raya", en: "Tic-tac-toe" }
  }
  players 2

  enum Mark { X, O }

  state {
    board: Grid[3, 3] of Mark? = none
    turn: Seat = 0
  }

  fn mark(p: Seat) -> Mark = X if p == 0 else O
  fn wins(m: Mark) -> Bool = any(line in lines(board, 3) : all(c in line : board[c] == m))
  fn full() -> Bool = all(c in cells(board) : not is_none(board[c]))

  flow {
    start -> Move

    decision Move {
      actor: turn
      action place(c in cells(board)) requires is_none(board[c]) { board[c] = mark(turn) }
      -> Win when wins(mark(turn))
      -> Draw when full()
      -> Move { turn = next(turn) }
    }

    terminal Win { payoff: win_loss(turn, 1, -1) }
    terminal Draw { payoff: fill(0) }
  }

  test "X gana en diagonal" {
    play place((0, 0)), place((0, 1)), place((1, 1)), place((0, 2)), place((2, 2))
    expect at(Win) and payoff == [1, -1]
  }

  /// X mueve primero: nunca tiene menos marcas que O ni más de una de ventaja
  invariant {
    let xs = count(c in cells(board) : board[c] == X)
    let os = count(c in cells(board) : board[c] == O)
    xs - os in 0..1
  }
}
```

Más ejemplos completos en [`games/`](../../games): Kuhn y Leduc (póker), Mentiroso, Dudo, Conecta 4,
Nim, la familia 2×2 (con `extends`) y el dilema del prisionero iterado (con `repeat`).

## 3. Léxico

- **Identificadores**: letras, dígitos y `_`, sin empezar por dígito. Por costumbre, tipos,
  valores de enumerado y nodos en `CamelCase`; lo demás en `snake_case`.
- **Palabras reservadas**: `action and assert auto case chance deal decision div else emit enum
  exit extend extends fail false flip flow fn for game if import in invariant let match meta
  move none not or override params phase players remove requires reveal reward shuffle
  simultaneous start state struct terminal test true when window`.
- **Palabras de contexto** (solo son palabras clave donde tocan, así que valen como nombres):
  `from to each as of top bottom at all face_up face_down face play expect legal illegal set seed
  where node per_player`, las claves de los miembros de un nodo y de `meta`, y `Grid`.
- **Números**: enteros (`42`, `1_000`) y decimales exactos (`0.5`, que es el racional 1/2; los
  pagos y los `Real` son racionales exactos). `div` es la división entera y `%` el módulo; `//`
  empieza un comentario.
- **Textos**: `"…"` con escapes `\n \t \r \" \\ \0 \u{…}`. Un **texto traducible** es
  `{ es: "…", en: "…" }` (entradas separadas por comas o por saltos de línea).
- **Comentarios**: `// …`, `/* … */` y **de documentación** `/// …`, que se pegan a la
  declaración siguiente (y llegan a la IR como `doc`). Para documentación traducible:
  `@doc({ es: "…", en: "…" })`.
- **Saltos de línea**: separan elementos y sentencias. Dentro de `( … )` y `[ … ]` no cuentan;
  dentro de `{ … }`, sí. Una expresión continúa en la línea siguiente tras un operador binario
  (`+`, `and`…) y tras `=`, `+=`…, `requires`, `when` y `clave:` (así parte las líneas el
  formateador). `;` también separa.

## 4. Archivos, módulos y paquetes

Un archivo `.game` contiene, en cualquier orden: `import`, `enum`, `struct`, `fn` de primer nivel,
juegos (`game Nombre { … }`) y juegos derivados con un combinador
(`game Nombre = repeat(…)`). Un archivo sin juegos es un **módulo** (`gamehub check` comprueba sus
tipos y funciones).

```game
import std.cards.{Card, Rank, french52}    // nombres concretos
import std.dice.*                          // todo lo que declara el módulo
import prisoners_dilemma.{PrisonersDilemma}
```

- **Resolución** de `a.b`: `std.…` es la [biblioteca estándar](../../stdlib/std); después, una
  **dependencia** `a` del paquete del archivo (`game.toml`); si no, el archivo `a/b.game` junto al
  que importa. En un `import` cada parte es un identificador: `prisoners_dilemma` encuentra
  también `prisoners-dilemma.game`. `import dep.{X}` lee el archivo principal de la dependencia;
  `import dep.sub.{X}`, `sub.game` dentro de ella.
- **Qué trae**: un nombre importado trae también lo que necesita del módulo (sus tipos y
  funciones auxiliares). Lo importado solo llega a la IR si el juego lo usa.
- **Ámbito de módulo**: las funciones de un módulo no ven el estado ni las opciones de ningún
  juego (sí `seats` y `num_players`); sus parámetros pueden llamarse como cualquier cosa del juego.
- Un nombre no se puede importar de dos módulos ni chocar con una declaración propia (E202); los
  ciclos de importación son un error (E504).

**Biblioteca estándar** (`stdlib/std/`, probada con [tests en Nomos](../../python/tests/fixtures/stdlib.game); la v0 de F2 y lo que añadió la Fase 6):

| Módulo | Contenido |
|---|---|
| `std.cards` | Baraja francesa (`Suit`, `Rank` del 2 al as, `Card`, `french52()`, `rank_value`, `is_red`), la del Skat (`skat32()`: del siete al as), la de Wizard (`WizardRank`, `WizardCard`, `wizard60()`, `is_wizard`, `is_jester`) y la española (`SpanishSuit`, `SpanishRank`, `SpanishCard`, `spanish40()`, `spanish48()`, `spanish_number`) |
| `std.dice` | `faces`, `count_face`, `count_with_wild` (comodines), `sum_face`, `most_repeated`, `all_same`, `is_straight` |
| `std.grid` | Direcciones (`orthogonal`, `diagonal`, `all_directions`), `shift`, `ray`, `manhattan`, `chebyshev`, `adjacent`, `touching` |
| `std.graph` | Grafos como listas de aristas: `neighbors_of`, `successors`, `connected`, `degree`, `cycle`, `advance` |
| `std.boards` | Tableros: direcciones de torre, alfil y dama, saltos de caballo (`rook_directions`, `bishop_directions`, `queen_directions`, `knight_jumps`), casillas dentro del tablero (`within`, `ray_within`, `hops_within`) y recorridos circulares (`loop_path`, `advance_on`, `passes`) |
| `std.tricktaking` | Bazas a partir del **palo efectivo** (un entero; −1 = se puede jugar siempre) y la **fuerza** que cada juego da a sus cartas: `can_play`, `first_suit`, `trick_key`, `trick_winner`, `trick_order` ([ADR-064](decisiones.md)) |
| `std.bidding` | Apuestas de bazas: `above`, `total_bid`, `all_bid`, `hook_ok` (la última apuesta no puede cuadrar el total), `sole_bidder` |
| `std.betting` | Botes con apuestas por asiento: `pot_levels`, `pots` (bote principal y secundarios), `pot_share`, `winnings`, `to_call` |
| `std.poker` | Manos de póquer de 5 a 7 cartas: `HandRank`, `hand_rank`, `hand_value` (un entero que ordena las manos; con [plugin nativo](#plugins-nativos)), y sus piezas (`encode`, `ranks_down`, `straight_high`, `top_ranks`, `flush_value`) |

### Plugins nativos

Una función de primer nivel se puede marcar como **nativa** ([ADR-062](decisiones.md)):

```game
@native("std.poker.hand_value")
fn hand_value(cards: List<Card>) -> Int { … }   // el cuerpo es la referencia, y es obligatorio
```

Un motor puede sustituir la función por un plugin que dé **exactamente** lo mismo para cualquier
entrada; si no lo tiene (o con `GAMEHUB_NATIVES=0`), usa el cuerpo. Los plugins son módulos
WebAssembly sin importaciones: el del módulo `a.b` es el archivo `a.b.wasm` de
`stdlib/std/native/` o de un directorio de `GAMEHUB_NATIVE_PATH`. El ABI está en el
[motor](motor.md#plugins-nativos).
La firma solo puede usar `Bool`, `Int`, `Seat`, `Cell`, enumerados, structs, tuplas, listas y
opcionales de ellos (E211). `gamehub natives list|check|build` los lista, los compara con la
referencia con entradas al azar y los compila desde WAT.

**Paquetes** ([`gamehub.packages`](../../python/src/gamehub/packages.py)): cada juego vive en un
directorio con su `game.toml`.

```toml
[game]
name = "iterated-pd"             # minúsculas y guiones (el id del juego)
version = "1.0.0"
entry = "iterated-pd.game"       # opcional: por defecto <name>.game
license = "CC-BY-4.0"
authors = ["GameHub"]
forked_from = "url@commit"       # lo escribe gamehub fork

[dependencies]
prisoners-dilemma = { path = "../prisoners-dilemma" }
cartas = { git = "https://…", rev = "v1.0" }    # rama, etiqueta o commit
```

`gamehub fetch` descarga las dependencias git (también las de las dependencias) en la caché
(`~/.cache/gamehub/git`) y escribe `game.lock` con el commit exacto de cada una; con el lock, la
compilación es reproducible (`--update` vuelve a resolver). `gamehub new` crea un paquete con un
juego que compila y pasa sus tests, a partir de una plantilla (`--template`: vacío, carrera
—la de por defecto—, tablero, cartas, dados o matriz 2×2; las mismas que el Studio); `gamehub clone` clona y descarga dependencias;
`gamehub fork` copia y anota el origen (`forked_from`, y el remoto original pasa a `upstream`).

## 5. Un juego por dentro

| Elemento | Forma | Notas |
|---|---|---|
| `meta` | `meta { id: "…", version: "…", title: …, description: …, authors: […], license: "…", tags: […] }` | `id` por defecto: el nombre en minúsculas con guiones (`TicTacToe` → `tic-tac-toe`); `version`, `"0.1.0"`. Textos traducibles en `title` y `description`. |
| `players` | `players 2` · `players 2..4` | Obligatorio. |
| `params` | `params { nombre: Tipo = valor … assert cond, "mensaje" }` | Opciones de la partida. Un valor por defecto solo usa opciones anteriores. Los `assert` se comprueban al crear la partida. |
| `enum` | `enum Palo { Oros, Copas, Espadas, Bastos }` | Ordenado por declaración (`ord`, comparaciones). |
| `struct` | `struct Card { suit: Suit, rank: Rank }` | Inmutable; literal `Card { suit: s, rank: r }`. |
| `state` | `state { [@visible(…)] [@size_visible(…)] nombre: Tipo [= valor] … }` | Sin valor: el cero del tipo (`false`, `0`, `""`, `none`, colección vacía, primer valor del enum…). En `per_player`, el valor puede usar `owner`. |
| `fn` | `fn nombre(p: T, …) -> R = expr` · `fn nombre(…) -> R { let … ; resultado }` | Puras; pueden leer estado y opciones; sin recursión (E208). |
| `flow` | `flow { start … nodos … }` | Ver §9. |
| `test` | `test "nombre" { pasos }` | Ver §10. No forman parte de la IR. |
| `invariant` | `[/// etiqueta] invariant cond` | Ver §10. |
| `ui` | `ui { destino: pista, … }` | Pistas de presentación para las interfaces (§12). No son reglas. |

Los nombres locales (parámetros de funciones y acciones, `let`, variables de comprensión) no
pueden ocultar un nombre global del juego (E204): estado, opciones, funciones, tipos, valores de
enumerado ni `seats`, `num_players`, `actor`, `viewer`, `owner`, `face_up`.

## 6. Tipos

| Tipo | Valores | Notas |
|---|---|---|
| `Bool`, `Int`, `Real`, `Text` | | `Real` = racional exacto; un `Int` vale donde se espera `Real`. |
| `Seat` | `0 … num_players - 1` | Intercambiable con `Int`. `next(s)`, `prev(s)`, `other(s)` (2 jugadores), `seats`, `seats_from(s)`. |
| `Cell` | `(fila, columna)` | Casilla de una rejilla; `c[0]` fila, `c[1]` columna; intercambiable con `(Int, Int)`. |
| `T?` | `none` o un `T` | `is_none(x)`, `unwrap(x)`. |
| `List<T>`, `Set<T>`, `Map<K, V>` | `[…]`, `set(…)`, — | |
| `Zone<T>` | colección **ordenada** de elementos con cara (mazo, montón, mesa) | `top(z)`, `size(z)`, `items(z)`; se baraja, se reparte, se voltea. |
| `Bag<T>` | multiconjunto **sin orden** (una mano) | Quien no ve su contenido solo ve su tamaño. |
| `(A, B, …)` | tuplas | `t[0]`, `t[1]` con índice constante. |
| `per_player T` | un `T` por asiento | `x[s]`; dueño de `x[s]` = `s` (para `@visible(owner)`). |
| `Grid[ancho, alto] of T` | rejilla | Dimensiones constantes o nombres de opciones (`Grid[columns, rows] of Disc?`). `cells`, `lines(g, k)`, `neighbors`, `in_bounds`. Se puede asignar con la lista de sus filas (`board = [[…], …]`, también en los `set` de los tests); las dimensiones se comprueban al ejecutar. |

Una lista vale donde se espera una zona, una bolsa, un conjunto o un `per_player`.

## 7. Visibilidad (información oculta)

Anotaciones en variables de estado, parámetros de acción y eventos:

| Anotación | Quién ve |
|---|---|
| `@visible(all)` | todos (por defecto) |
| `@visible(none)` | nadie (un mazo) |
| `@visible(owner)` | el dueño de cada parte `per_player` (una mano) |
| `@visible(face_up)` | en una zona, lo que está boca arriba |
| `@visible(expr)` | quien cumpla `expr`, con `viewer`, `owner`, `face_up` y `at(Nodo)`: `@visible(viewer == owner or at(Showdown))` |
| `@size_visible(…)` | en zonas y bolsas, quién ve el tamaño (por defecto, todos) |

En acciones: `action play(@visible(none) @size_visible(all) cards in …)` oculta qué cartas se
jugaron pero no cuántas. En eventos: `@visible(owner) emit …`. `reveal x to all` /
`reveal x to s [as "etiqueta"]` muestran un valor. Los envíos de un nodo `simultaneous` y las
respuestas de una ventana `collect` quedan ocultos hasta resolverse. `gamehub check` avisa de
posibles fugas (W405, §15).

## 8. Expresiones

**Precedencia** (de menor a mayor): `a if c else b` · `or` · `and` · `not` · comparaciones
(`== != < <= > >= in` `not in`; no se encadenan) · rangos (`a..b` inclusivo, `a..<b`) ·
`+ -` · `* / div %` · `-` unario · llamadas, índices, cortes y campos (`f(x)`, `xs[i]`, `xs[a:b]`,
`c.rank`). Los paréntesis agrupan; `(a, b)` es una tupla.

| Construcción | Ejemplo |
|---|---|
| Literales | `true`, `none`, `3`, `0.25`, `"texto"`, `[1, 2]`, `(f, c)`, `Card { suit: s, rank: r }` |
| Enumerados | `Rank.Ace` (siempre) o `Ace` (si no es ambiguo, E203); `Rank.values` |
| Condicional | `1 if ganó else 0` |
| `case` | `case { x > y => 1  x < y => -1  else => 0 }` (una rama por línea) |
| `match` | `match (a, b) { (Red, _) => 1 … }` — patrones: valores, `_` y tuplas; tiene que ser exhaustivo (E304) |
| Bloque con `let` | `{ let xs = …; let os = …; xs - os }` |
| Comprensión | `[c.value for c in hand[s] if c.rank != Ace]`, varios `for` e `if` |
| Agregados | `all(x in xs : p)`, `any`, `count`, `sum`, `max`, `min`, `argmax`, `argmin`, `sort_by`, `map`, `filter`, `flat_map`; atajos `sum(xs)`, `max(xs)`, `min(xs)` |
| Colecciones | `xs + ys` (concatenar), `xs - ys` (diferencia), `x in xs`, `x not in xs` |
| Contexto | `actor` (acciones y transiciones de una decisión), `seats`, `num_players`, `at(Nodo)`; en visibilidad: `viewer`, `owner`, `face_up` |

**Funciones predefinidas**: `len`, `size`, `items`, `top`, `first`, `last`, `only`, `reverse`,
`distinct`, `append`, `concat`, `union`, `intersection`, `difference`, `subsets(xs, min, max)`,
`range(a, b)`, `slice`, `contains`, `set(…)`, `abs`, `min`, `max`, `sum`, `rat(a, b)`,
`is_none`, `unwrap`, `ord`, `next`, `prev`, `other`, `seats_from`, `cells`, `lines`,
`neighbors`, `in_bounds`, `cell(f, c)`, `win_loss(ganador, gana, pierde)`, `fill(valor)`; y, solo
como lado derecho de una asignación en azar, `roll(n)`, `random(xs)`, `sample([(valor, prob), …])`.

## 9. Efectos y flow

**Sentencias** (en `start { … }`, nodos `chance`/`auto`, acciones, `resolve`, `on_enter`,
`on_exit` y transiciones):

| Sentencia | Notas |
|---|---|
| `let x = e` | local al bloque |
| `x = e`, `x += e`, `x -= e`, `x *= e` | sobre estado: variable, índice o campo (`hand[s]`, `pos.x`); `+=` concatena listas |
| `if c { … } else if … else { … }` · `for x in xs { … }` | |
| `move SEL from Z1 to Z2 [at top\|bottom]` | `SEL`: `all`, `top n`, `bottom n`, `at i`, un valor o una lista de valores |
| `flip SEL of Z face_up\|face_down\|face(b)` | |
| `shuffle Z` · `x = roll(6)` · `x = random(xs)` · `x = sample(…)` | aleatorias: solo en nodos `chance` y en `start { … }` (E306) |
| `deal n from Z to each H` · `deal all from Z to each H` | una carta cada vez, en ronda |
| `reveal e to all\|s [as texto]` · `[@visible(…)] emit nombre { campo: e, … }` | información y eventos |
| `reward e to s` · `fail "texto"` | `fail` = error de reglas (un caso que el diseño no contempla) |

**Flow**:

```game
flow {
  start [{ preparación }] -> Nodo
  decision N { actor: e  action …  -> … }
  simultaneous N { actors: e  action …  resolve { … }  -> … }
  window N { eligible: e  mode: priority|collect|race  [order: e]  action …  -> … }
  chance N { efectos aleatorios  -> … }
  auto N { efectos  -> … }
  phase N { start -> M  [on_enter { … }]  [on_exit { … }]  nodos…  -> … }
  terminal N { [let x = e]  payoff: e  [rank: e] }
}
```

- **Acciones**: `action nombre(p: Tipo in dominio, …) requires cond { efectos  -> transiciones }`.
  El dominio de cada parámetro es una colección finita que puede depender de los anteriores; con
  un enumerado o `Bool` basta el tipo (`c: Choice`); con dominio basta el dominio
  (`c in cells(board)`). Las transiciones de una acción van al final de su cuerpo.
- **Transiciones**: `-> Destino [when cond] [{ efectos }]`, en orden; gana la primera que se
  cumple. Tras una acción se prueban primero las de la acción y después las del nodo. Una
  transición sin `when` seguida de otras es un error (E403); si todas tienen condición, `check`
  avisa (W402). `-> exit` sale de la fase: se ejecuta su `on_exit` y después sus transiciones.
- **Nodos**: `decision` (un actor), `simultaneous` (todos a la vez, en secreto; sin transiciones
  por acción), `window` (reacción: pasar es implícito; `priority` por orden, `collect` en secreto,
  `race` el primero), `chance` (azar), `auto` (sin espera), `phase` (subdiagrama), `terminal`
  (pagos: un número por asiento). La semántica exacta, en [motor §5](motor.md#5-semántica-del-flow).

## 10. Tests e invariantes

```game
test "la carta alta gana" {
  players 2                                       // configuración, al principio
  params { max_play: 2 }
  seed 7
  chance where only(hand[0]) == K and only(hand[1]) == J
  play check(), bet(), call()                     // el asiento: el único que puede actuar
  play 0: choose(Defect), 1: choose(Cooperate)    // o indicado
  expect at(Showdown) and payoff == [2, -2]
  expect legal call()
  expect illegal raise()
  set hand[0] = [Card { suit: Clubs, rank: Ace }] // cambiar el estado a mano
}

/// Las cartas no se pierden
invariant size(deck) + sum(s in seats : size(hand[s])) == 3
```

- `players`, `params` y `seed` van al principio (E601); por defecto, el mínimo de jugadores, las
  opciones por defecto y la semilla 0.
- Antes de cada paso, el azar pendiente se resuelve con PCG32(semilla). `chance [r, …]` fija el
  resultado; `chance where c` elige uno que cumpla `c`, con su probabilidad condicionada (por
  enumeración o, si hay demasiados resultados, probando al azar).
- En `expect` y en los argumentos de las acciones existen `payoff` (solo al final) y `active`.
- Tras un `set` el test deja de comprobar los invariantes (el estado puede no ser alcanzable).
- Los **invariantes** se comprueban en cada estado que alcanza un test y en partidas aleatorias
  (`gamehub test --playouts N`, 20 por defecto, rotando el número de jugadores).

Los fallos se explican al estilo rustc, con los valores en juego
(`` `payoff == [1, -1]` es falso: `payoff` vale [2, -2] ``) y las jugadas legales.

## 11. Mods y combinadores

```game
import tictactoe.{TicTacToe}

game Misere extends TicTacToe {
  meta { title: "Tres en raya inverso" }
  override terminal Win { payoff: win_loss(turn, -1, 1) }
}

game WithPass extends TicTacToe {
  state { passed: per_player Bool = false }
  extend node Move {
    action skip() requires not passed[actor] { passed[actor] = true }
  }
}

game IteratedPD = repeat(PrisonersDilemma, rounds: 10, payoff: sum)
game Match = best_of(PrisonersDilemma, rounds: 3)
```

- **`extends`**: la variante parte de la base (del archivo, importada o un combinador) y aplica en
  orden: declaraciones nuevas (no pueden llamarse como una de la base), `override` (fn, enum,
  struct, un nodo —también dentro de fases—, `params`, `state`; un `override params` con
  `assert` sustituye las restricciones de la base), `remove node|fn|state|param|enum|struct X` y
  `remove action Nodo.accion`, y `extend node X { … }` (acciones al final, transiciones
  **delante** de las de la base). `meta` se mezcla (sin heredar `id` ni `version`); tests e
  invariantes no se heredan. Errores E505.
- **`repeat(Base, rounds: n, payoff: sum|mean)`** y **`best_of(Base, rounds: n)`** transforman la
  IR: una fase por ronda que devuelve el estado a su valor inicial, terminales que apuntan el
  resultado y un terminal final (suma o media; o `num_players - 1` para quien gana más rondas y
  `-1` para el resto). `rounds` pasa a ser una opción del juego. Un combinador no lleva tests:
  se extiende (`game Pruebas extends IteratedPD { test … }`). Errores E506.

## 12. Presentación: `ui { … }`

Pistas para las interfaces: cómo dibujar el estado, cómo se llaman las cosas en pantalla y cómo
se eligen los argumentos de una acción tocando el tablero. **No son reglas**: llegan a la IR en
la clave `ui`, que no cuenta para el hash de reglas, y las lee la UI genérica de la web
(`@gamehub/auto-ui`). Sin ellas el juego se juega igual: la UI genérica deduce casi todo de los
tipos y de los dominios de las acciones (`cells(board)` → pulsar casillas; `subsets(items(mano))`
→ elegir cartas de la mano).

```game
ui {
  board: grid
  cup: dice, label({ es: "Cubilete", en: "Cup" })
  dice_left: counter, place(seats)
  die: hidden
  rank: place(top)
  dice: label({ es: "Dados por jugador", en: "Dice per player" })   // una opción
  Mark: symbols(X: "✕", O: "◯")
  Disc: colors(Red: "#e53935", Yellow: "#fdd835"), labels(Red: "Rojas", Yellow: "Amarillas")
  Card: card(rank: rank, suit: suit)
  action bid: label({ es: "Apostar", en: "Bid" })
  action drop.c: column(board)
  node Bid: label({ es: "Apuestas", en: "Bidding" })
  seats: colors("#e53935", "#fdd835"), names("Rojas", "Amarillas")
}
```

Cada línea es `destino: pista, pista…`. `ui` solo es palabra clave al empezar la sección.

| Destino | Pistas |
|---|---|
| variable de estado | **cómo dibujarla** (una): `grid` (rejilla), `hand` (abanico), `pile` (montón con la de arriba), `deck` (mazo boca abajo), `row` (en fila), `dice` (dados: un `Int` o una colección de `Int`), `counter` (número), `chips` (fichas de apuesta), `seat` (un jugador), `hidden` (no se dibuja); `place(table \| seats \| top)` (en la mesa, en el panel de cada asiento —solo `per_player`— o en la barra de arriba); `label(texto)` |
| opción (`params`) | `label(texto)` |
| enumerado | `symbols(Valor: "…", …)`, `colors(Valor: "#rrggbb", …)`, `labels(Valor: texto, …)`, `card` (sus valores son cartas), `label(texto)` |
| struct | `card(rank: campo, suit: campo)` (carta de baraja: el campo con el valor y, si hay, el del palo), `label(texto)` |
| `action nombre` | `label(texto)` |
| `action nombre.parámetro` | `label(texto)`; cómo elegirlo: `cell(rejilla)` (pulsar una casilla; el parámetro es `Cell`), `column(rejilla)` / `row(rejilla)` (pulsar en una columna o fila; el parámetro es `Int`), `pick(zona)` (elegir de una colección: un elemento o una lista de ellos) |
| `node Nombre` | `label(texto)` |
| `seats` | `colors("#…", …)` (un color por asiento), `names(texto, …)` (p. ej. «Blancas», «Negras») |

Errores: destino desconocido, con sugerencia (E701); pista que no vale para ese destino o tipo
(E702); argumentos inválidos —valor de enumerado, campo o color que no existe, `place(seats)` en
algo que no es `per_player`, `column(x)` para un parámetro que no es `Int`…— (E703); dos pistas del
mismo hueco (dos formas de dibujo, dos `label`…) (E704). En una variante (`extends`), cada pista
sustituye a la del mismo hueco en la base.

## 13. Herramientas

| Comando | Qué hace |
|---|---|
| `gamehub check RUTA…` | Compila y comprueba (tipos, flow, avisos estáticos, clasificación); `--format json` para editores |
| `gamehub fmt RUTA…` | Formato canónico (`--check`, `--diff`, `--stdin`) |
| `gamehub test RUTA…` | Tests e invariantes (`--playouts`, `--seed`, `-k`, `--format json`) |
| `gamehub compile` / `decompile` | `.game` ↔ IR (`.ir.json`); la vuelta es exacta |
| `gamehub viz JUEGO` | Diagrama del flow (Mermaid o `--format dot`) |
| `gamehub rules JUEGO` | Reglamento en Markdown (`--lang en`) |
| `gamehub diff A B` · `gamehub diff REV1..REV2 archivo` | Diff semántico (texto o JSON) |
| `gamehub new` · `fetch` · `clone` · `fork` | Paquetes (`new --template vacio\|carrera\|tablero\|cartas\|dados\|matriz`) |
| `gamehub play` · `fuzz` · `replay` | Jugar en la terminal, partidas aleatorias (`fuzz --jobs N` en varios procesos), replays (aceptan `.game`) |
| `gamehub perft JUEGO --depth N` | Cuenta las secuencias de jugadas legales (`--divide`, `--skip`, `--jobs`, `--param`); los puntos de azar suman todos sus resultados |
| `gamehub natives list\|check\|build` | Plugins nativos: cuáles hay, si coinciden con la referencia (`--trials`), compilar WAT a WASM (`--check`, `--write`) |
| `gamehub studio [RUTA]` | El [Studio](studio-editor-visual.md): diseñar con el diagrama y el texto a la vez y simular (`--open`, `--port`) |
| `gamehub lsp` | Servidor de lenguaje por la entrada estándar, para cualquier editor con LSP |

El servidor de lenguaje da diagnósticos, autocompletado según dónde está el cursor (también con
el texto a medias), hover con tipos y firmas, ir a la definición (también en la biblioteca
estándar), referencias, renombrar (comprobando choques y que el juego siga compilando), formato,
esquema del documento, plegado, ayuda de firmas y arreglos rápidos. Extensión de VS Code:
[`editors/vscode/nomos`](../../editors/vscode/nomos) (resaltado, diagnósticos al guardar y
formato; todavía con `gamehub check` y `gamehub fmt`, no con el LSP).

## 14. Traducción a la IR

El comprobador elabora y traduce en una sola pasada; lo que no aparece aquí se traduce 1:1.

| Nomos | IR |
|---|---|
| `a + b + c` | `["add", a, b, c]` (las cadenas se aplanan salvo que el izquierdo vaya entre paréntesis) |
| `-5`, `0.25`, `a..<b` | `["const", -5]`, `["rat", 1, 4]`, `["range", a, b - 1]` |
| `xs + ys`, `xs - ys`, `x in xs`, `x not in xs` | `concat`, `difference`, `["contains", xs, x]`, `["not", ["contains", …]]` |
| `x += e` | `["assign", x, ["add", x, e]]` (o `concat` en listas) |
| `deal n from Z to each H` | bucles de `move top 1` por asiento (`deal all`: hasta vaciar Z, en ronda) |
| `match` | `case` (si es exhaustivo, la última rama es el caso por defecto) |
| `max(x in xs : e)`, `sum(xs)` | `["max_of", "x", xs, e]`, `["sum", "x", xs, ["local", "x"]]` |
| `{ let x = e; r }` | `["let", "x", e, r]` |
| `[e for x in xs if c]` | `["map", "x", ["filter", "x", xs, c], e]` |
| `next(s)`, `other(s)` | `["next_seat", s]`, `["other_seat", s]` |
| variables sin valor inicial | el cero del tipo |
| declaraciones de módulo no usadas | no llegan a la IR |
| `test`, `invariant`, comentarios | no llegan a la IR (los `///` sí, como `doc`) |

## 15. Diagnósticos

Al estilo de `rustc`: código, mensaje, posición con el trozo subrayado, notas y ayuda. Los
errores de un archivo se informan todos (el parser se recupera al nivel del bloque en el que
está).

| Códigos | Familia |
|---|---|
| E101–E103 | léxico: carácter inesperado, comentario o texto sin cerrar, escape desconocido |
| E110–E112 | sintaxis: elemento inesperado, anotación no permitida, orden en una acción |
| E201–E211 | nombres y declaraciones: desconocido (con sugerencia), duplicado o choque, ambiguo, oculta un global, fuera de su contexto (`actor`, estado en funciones de módulo…), reservado, aridad, recursión, struct sin valores, jugadores, firma que no puede ser `@native` |
| E301–E307 | tipos: incompatibles, operador no aplicable, no recorrible, `match` no exhaustivo o rama inalcanzable, dominio no finito, azar fuera de lugar, asignación a algo que no es estado |
| E401–E406 | flow: nodos duplicados o vacíos, miembros no válidos, transiciones inalcanzables o `-> exit` fuera de fase, nodos sin salida, `start` y `flow`, acciones repetidas o en el sitio equivocado |
| E502–E507 | módulos, mods y paquetes: `override` sin `extends`, módulo no encontrado, importación circular, mods (E505), combinadores (E506), dependencias (E507) |
| E601–E602 | tests: configuración fuera de lugar, número de jugadores |
| E701–E704 | presentación (`ui`): destino desconocido, pista que no vale ahí, argumentos inválidos, pista repetida |
| E610–E614 | fallos al ejecutar tests (`gamehub test`): lo esperado no se cumple, jugada imposible, azar, invariante, error de reglas |
| E900 | error interno: la IR generada no es válida (un fallo de GameHub) |
| W101 | `@size_visible` en algo que no es zona ni bolsa |
| W401–W407 | avisos de `gamehub check`: nodo inalcanzable, transiciones que pueden no cubrir todos los casos, nodo sin camino a un final, bucle de nodos automáticos sin efectos, posible fuga de información, declaración sin usar, transición tapada (en IR escrita a mano) |

**Fugas de información (W405, v1)**: un dato oculto que llega a estado o eventos visibles para
todos (también a través de un `if`), que decide quién juega o por qué nodo sigue la partida, o del
que dependen las jugadas legales de quien no lo ve. No cuentan el tamaño de lo que tiene tamaño
visible, la parte del actor de una variable `@visible(owner)` ni lo revelado antes con
`reveal … to all` en el mismo bloque.

## 16. Formato canónico

`gamehub fmt` (idempotente, conserva los comentarios y las líneas en blanco que los separan):
sangría de 2 espacios, 100 columnas, una declaración o sentencia por línea, como mucho una línea
en blanco seguida. Un nodo con un solo miembro, una acción con una sola sentencia simple y una
transición con una sola sentencia simple van en una línea si caben. Si una expresión no cabe:
tras `=` o `clave:` el valor pasa a la línea siguiente (o, si empieza por un corchete y tampoco
cabe allí, se abre en la misma línea y se parte por dentro); una cadena aritmética reparte sus
operandos rellenando líneas; una de `and`/`or`, uno por línea; las condiciones seguidas de un
bloque llevan sangría doble.

## 17. Diferencias con el RFC de la Fase 0

| RFC (Fase 0) | v0.1 |
|---|---|
| `roll d6 into x`, `draw_random c from Z` | `x = roll(6)`, `x = random(xs)`, `x = sample(…)` |
| `payoff: table (…) { … }`, `zero_sum(winner: …)` | `match` / `case` y `win_loss(ganador, gana, pierde)` |
| `action play(cards: subset(hand, size: 1..4))` | `action play(cards in subsets(items(hand[actor]), 1, 4))` |
| `move_all Z1 to Z2`, `log "…"` | `move all from Z1 to Z2`, `emit` |
| `mode: priority(order)`, `phase … for r in …`, `call Modulo.Subflow` | `mode: …` + `order: …`; fases con transiciones; subflujos: pendiente |
| `import std.tricktaking as tt` (alias), `roles`/`teams`, `deck` | pendiente (sin alias; roles y barajas declarativas llegan con su fase) |
| `ui { … }` | pistas de presentación con destino (§12), desde la Fase 4 |

Decisiones relacionadas: [ADR-017, ADR-018](decisiones.md) (nombre y llaves) y ADR-027 a ADR-034
(implementación, Fase 2).
