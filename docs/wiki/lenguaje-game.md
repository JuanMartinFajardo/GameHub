# Nomos — el lenguaje `.game`

> Estado: **RFC de sintaxis v0.1 aprobado** (2026-10-09; [ADR-017](decisiones.md), [ADR-018](decisiones.md)).
> El compilador llega en la Fase 2. La semántica está en el [modelo formal](modelo-formal.md); el
> texto compila a [GameIR](ir.md), cuyo núcleo ya está especificado en [`spec/ir/v0`](../../spec/ir/v0).

## 1. Objetivos de diseño

- **Legible por humanos** y **diffeable** (un cambio de regla = un diff pequeño).
- **Correspondencia 1:1 con el diagrama de flujo:** cada `node` es una caja y cada `->` una flecha
  con su guarda. Por eso el editor visual y el texto pueden ser dos vistas del mismo juego.
- **Expresiones puras, tipadas y totales**; efectos solo en bloques `{ … }` de efectos.
- Sintaxis con llaves, palabras clave en inglés, expresiones al estilo Python (`and`, `or`, `not`,
  `in`, `if … else …`). Textos visibles para jugadores, traducibles (`es`, `en`…).

## 2. Estructura de un archivo

```
game <Nombre> {
  meta { … }            // título, versión, autores, etiquetas, licencia
  params { … }          // parámetros y variantes (con validaciones)
  players …             // nº de asientos: 2 | 3..6 | param n
  roles / teams { … }   // opcional
  enum / struct …       // tipos
  deck …                // componentes (barajas, fichas)
  state { … }           // esquema de estado + visibilidad
  fn …                  // funciones puras
  flow { … }            // el diagrama de flujo (statechart)
  ui { … }              // pistas de renderizado (opcional, no afecta a las reglas)
  test "…" { … }        // tests de reglas
}
```

## 3. Tipos

| Tipo | Ejemplo | Notas |
|---|---|---|
| Primitivos | `Bool`, `Int`, `Real`, `Text` | `Real` racional/decimal exacto en pagos |
| Asiento | `Seat` | `next(s)`, `prev(s)`, `other(s)` (2 jug.), `seats`, `num_players` |
| Enumerados | `enum Suit { Oros, Copas, Espadas, Bastos }` | Ordenados por declaración |
| Registros | `struct Card { suit: Suit, rank: Rank }` | Inmutables |
| Opcional | `Mark?` | `none` |
| Colecciones | `List<T>`, `Set<T>`, `Map<K,V>` | |
| Zona | `Zone<Card>` | Colección **ordenada** con posiciones públicas (mazo, pila, fila de Memory) |
| Bolsa | `Bag<Card>` | Multiconjunto **sin orden** (una mano): quien no ve su contenido solo ve su tamaño |
| Por jugador | `per_player T` | Azúcar de `Map<Seat,T>` con noción de *dueño* |
| Tableros | `Grid[8, 8] of Piece?`, `Graph<Square>` | `cells`, `neighbors`, `ray(dir)`, `lines(len)` |
| Rangos | `0..n` (inclusivo), `0..<n` | |

## 4. Visibilidad

Anotaciones sobre el estado (o sobre parámetros de acción y eventos):

```
@visible(all)                 // por defecto
@visible(none)                // nadie (p. ej. el mazo)
@visible(owner)               // el dueño en per_player / zonas con dueño
@visible(team_of(owner))
@visible(seats: {dealer})     // un conjunto calculado
@visible(all if at(Showdown) else owner)   // dependiente del estado/nodo
@size_visible(all)            // en zonas: el tamaño es público aunque el contenido no
```

Efectos relacionados: `reveal x to all`, `reveal x to {s}`, `flip c face_up`.

## 5. Flow

```
flow {
  start -> Nodo                        // o: start { efectos de preparación } -> Nodo

  decision Nombre {                    // un actor
    actor: expr
    action nombre(p: Dominio, …) requires guarda { efectos } [-> Destino]
    -> Destino when cond { efectos }   // transiciones en orden; la última puede no tener `when`
  }
  simultaneous Nombre { actors: expr; action …; resolve { … }; -> … }
  window Nombre { eligible: expr; mode: priority(order) | collect | race; action …; action pass; -> … }
  chance Nombre { shuffle deck; roll d6 into x; … ; -> … }
  auto Nombre { efectos; -> … }
  phase Nombre [for r in 1..R | repeat until cond] { start -> …; nodos…; on_enter {…}; on_exit {…} }
  call Modulo.Subflow(args) -> Destino
  terminal Nombre { payoff: expr; rank: expr }
}
```

`-> exit` sale de la `phase` actual. Dentro de una acción, `actor` es quien actúa.

## 6. Efectos (sentencias)

`x = e` · `x += e` · `let y = e` · `if c { … } else { … }` · `for x in col { … }` ·
`move c from Z1 to Z2 [top|bottom]` · `move_all Z1 to Z2` · `deal n from Z to each hand` ·
`shuffle Z`* · `roll d6 into x`* · `draw_random c from Z`* · `reveal …` · `emit Evento{…} @visible(…)` ·
`reward s += e` · `log "…"` &nbsp;&nbsp;(* solo en nodos `chance` / `start`)

## 7. Ejemplos

### 7.1 Tres en raya (información perfecta, determinista)

```game
game TicTacToe {
  meta { title: "Tres en raya", version: "1.0.0", tags: [classic] }
  players 2

  enum Mark { X, O }

  state {
    board: Grid[3, 3] of Mark? = none
    turn:  Seat = 0
  }

  fn mark(p: Seat) -> Mark = X if p == 0 else O
  fn wins(m: Mark) -> Bool = any(line in lines(board, 3) : all(c in line : board[c] == m))

  flow {
    start -> Move

    decision Move {
      actor: turn
      action place(c: Cell(board)) requires board[c] == none {
        board[c] = mark(turn)
      }
      -> Win  when wins(mark(turn))
      -> Draw when all(c in cells(board) : board[c] != none)
      -> Move { turn = next(turn) }
    }

    terminal Win  { payoff: zero_sum(winner: turn) }   // +1 ganador, -1 perdedor
    terminal Draw { payoff: all(0) }
  }

  test "X gana en diagonal" {
    play place((0,0)), place((0,1)), place((1,1)), place((0,2)), place((2,2))
    expect at(Win) and payoff == [1, -1]
  }
}
```

### 7.2 Dilema del prisionero (simultáneo, suma no nula)

```game
game PrisonersDilemma {
  meta { title: "Dilema del prisionero", version: "1.0.0" }
  players 2

  params {
    T: Real = 5;  R: Real = 3;  P: Real = 1;  S: Real = 0
    assert T > R and R > P and P > S and 2*R > T + S
  }

  enum Choice { Cooperate, Defect }

  state {
    choice: per_player Choice? = none   // un nodo simultaneous oculta los envíos hasta resolverse
  }

  flow {
    start -> Choose

    simultaneous Choose {
      actors: seats
      action choose(c: Choice) { choice[actor] = c }
      -> End
    }

    terminal End {
      payoff: table (choice[0], choice[1]) {
        (Cooperate, Cooperate) => (R, R)
        (Cooperate, Defect)    => (S, T)
        (Defect,    Cooperate) => (T, S)
        (Defect,    Defect)    => (P, P)
      }
    }
  }
}

// Combinador: dilema iterado de 200 rondas, pago = suma, se observa el historial público.
game IteratedPD = repeat(PrisonersDilemma, rounds: 200, payoff: sum)
```

### 7.3 Póker de Kuhn (azar + información oculta)

```game
game KuhnPoker {
  meta { title: "Póker de Kuhn", version: "1.0.0", tags: [benchmark] }
  players 2

  enum Card { J, Q, K }                         // J < Q < K
  enum Move { Check, Bet, Call, Fold }

  state {
    @visible(none) @size_visible(all) deck: Zone<Card> = [J, Q, K]
    @visible(owner) hand: per_player Bag<Card>
    put:   per_player Int = 1                   // fichas aportadas (ante incluido)
    moves: List<Move> = []
  }

  flow {
    start -> Deal

    chance Deal {
      shuffle deck
      deal 1 from deck to each hand
      -> Act
    }

    decision Act {
      actor: len(moves) % 2                     // alternan 0, 1, 0
      action check() requires moves == [] or moves == [Check]  { moves += [Check] }
      action bet()   requires moves == [] or moves == [Check]  { moves += [Bet];  put[actor] += 1 }
      action call()  requires last(moves) == Bet               { moves += [Call]; put[actor] += 1 }
      action fold()  requires last(moves) == Bet               { moves += [Fold] }
      -> Fold     when last(moves) == Fold
      -> Showdown when moves == [Check, Check] or last(moves) == Call
      -> Act
    }

    terminal Fold {                             // gana quien no se retiró y cobra lo que puso el otro
      let folder = (len(moves) - 1) % 2
      payoff: zero_sum(winner: other(folder), amount: put[folder])
    }
    terminal Showdown {
      let w = argmax(s in seats : only(hand[s]))
      payoff: zero_sum(winner: w, amount: put[other(w)])
    }
  }
}
```

### 7.4 Mentiroso (*Bullshit*: parámetros ocultos + ventana de reacción)

Reglas: por turnos, cada jugador pone de 1 a 4 cartas boca abajo en el centro declarando que son
del rango que toca ("3 cuatros"); el rango avanza As, Dos, Tres… Cualquiera puede gritar
"¡Mentiroso!": si era mentira, quien jugó se lleva el montón; si era verdad, se lo lleva quien
acusó. Gana quien se queda sin cartas sin ser pillado. Versión ejecutable en IR:
[`mentiroso.ir.json`](../../spec/ir/examples/mentiroso.ir.json).

```game
game Mentiroso {
  meta { title: "Mentiroso", version: "0.1.0", tags: [cards, bluffing] }
  players 3..6
  params { max_play: Int = 4 }

  enum Suit { Clubs, Diamonds, Hearts, Spades }
  enum Rank { Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Jack, Queen, King }
  struct Card { suit: Suit, rank: Rank }

  state {
    @visible(none)  deck: Zone<Card> = [Card { suit: s, rank: r } for s in Suit, r in Rank]
    @visible(owner) hand: per_player Bag<Card>         // el tamaño es público por defecto
    @visible(none)  pile: Zone<Card> = []              // montón boca abajo
    turn: Seat = 0
    rank: Rank = Ace                                   // rango que toca declarar
    last_by: Seat = 0
    last_count: Int = 0                                // cuántas cartas se jugaron (se ve)
    winner: Seat = 0
  }

  fn next_rank(r: Rank) -> Rank = Rank.values[(ord(r) + 1) % len(Rank.values)]
  fn last_play() -> List<Card> = items(pile)[0 : last_count]
  fn truthful() -> Bool = all(c in last_play() : c.rank == rank)

  flow {
    start -> Deal

    chance Deal {
      shuffle deck
      deal all from deck to each hand                  // una a una, en ronda
      -> Play
    }

    decision Play {
      actor: turn
      action play(cards: subset(hand[actor], size: 1..max_play) @visible(none) @size_visible(all)) {
        move cards from hand[actor] to pile
        last_by = actor
        last_count = len(cards)
        emit claim { seat: actor, count: len(cards), rank: rank }      // "3 cuatros"
      }
      -> Challenge
    }

    window Challenge {
      eligible: seats - [last_by]
      mode: collect(order: seats_from(next(last_by)) - [last_by])     // deciden a la vez
      action liar() {                                                 // "¡Mentiroso!"
        reveal last_play() to all
        if truthful() { move_all pile to hand[actor] }                // acusó en falso
        else          { move_all pile to hand[last_by] }              // era mentira
      }
      -> End  when len(hand[last_by]) == 0 { winner = last_by }
      -> Play { turn = next(turn); rank = next_rank(rank) }
    }

    terminal End { payoff: [1 if s == winner else 0 for s in seats] }
  }
}
```

Pasar es implícito en las ventanas. Variantes previstas como parámetros (pendientes de confirmar,
[pregunta 9b](preguntas-abiertas.md)): rango libre o elegido al abrir ronda, quién puede acusar,
quién juega tras una acusación, baraja española.

## 8. Modularidad

```game
import std.cards.{Spanish40, Suit, Rank}      // barajas: French52, Spanish40/48, Skat32, Wizard60
import std.tricktaking as tt                  // sub-flows: tt.Trick, funciones: tt.must_follow

game WizardVariant extends Wizard {           // un mod = herencia + parches
  override params { rounds: Int = 10 }
  override fn score(bid: Int, won: Int) -> Int = 30 + 10*won if bid == won else -10*abs(bid - won)
  remove node DealerChoosesTrump
}
```

**Combinadores de juegos:** `repeat(G, rounds, payoff)`, `best_of(G, n)`, `sum(G1, G2)` (suma
disyuntiva de CGT), `sequence(G1, G2)`, `with_params(G, …)`.

## 9. Herramientas previstas

`gamehub check` (tipos, alcanzabilidad, exhaustividad, terminación, fugas de información) ·
`gamehub fmt` (formateador canónico, conserva comentarios) · `gamehub test` · `gamehub viz`
(diagrama Mermaid/SVG) · resaltado y LSP para VS Code / Monaco.

## 10. Decisiones de sintaxis

| Tema | Decisión | Estado |
|---|---|---|
| Nombre | **Nomos**, archivos `.game` | Aceptada (ADR-017) |
| Bloques | Llaves | Aceptada (ADR-018) |
| Palabras clave | Inglés; textos de jugador traducibles | Aceptada (ADR-018) |
| Condicional | `X if c else Y` (estilo Python) | Por defecto |
| Expresiones de colección | Comprensiones `[e for x in xs if c]`, cuantificadores `all(x in xs : p)`, cortes `xs[a : b]`, literales `Card { suit: s, rank: r }` | Por defecto |
| Números | Pagos exactos (racionales) en la IR; `double` en el core C++ | Por defecto |
