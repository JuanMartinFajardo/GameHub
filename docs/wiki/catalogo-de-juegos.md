# Catálogo de juegos

> Estado: **ola 1 completa** (Fase 2, 2026-10-09). Los 16 juegos de la ola 1 están en Nomos en
> [`games/`](../../games), cada uno un paquete con sus tests, y se juegan en la terminal
> (`gamehub play`). Los de la ola 2 llegan en la Fase 6.
> El orden está pensado para que cada ola fuerce **nuevas capacidades del motor** de forma incremental.

Leyenda: **Az** = azar · **Oc** = información oculta · **Si** = simultaneidad/ventanas.

## Ola 1 — Motor y lenguaje mínimos (Fases 1–2)

| Juego | Jug. | Az | Oc | Si | Qué pone a prueba |
|---|---|:-:|:-:|:-:|---|
| Tres en raya (y *m,n,k*) | 2 | | | | Rejilla, líneas, terminales, parámetros de tamaño; **resolver por minimax** |
| Piedra-papel-tijera | 2 | | | ✓ | Nodo `simultaneous`; NE mixto |
| Dilema del prisionero (+ iterado) | 2 | | | ✓ | Parámetros con `assert`; tabla de pagos; combinador `repeat`; torneo Axelrod |
| Familia 2×2 (pares o nones, gallina, caza del ciervo, batalla de los sexos) | 2 | | | ✓ | Un mismo juego parametrizado por matriz; variantes con `extends` |
| Nim | 2 | | | | Parámetros de montones; **Sprague–Grundy** |
| Conecta 4 | 2 | | | | "Gravedad", estado mayor; alfa-beta con heurística |
| Póker de Kuhn | 2 | ✓ | ✓ | | Azar, manos privadas (bolsas), vistas redactadas; **CFR** (valor −1/18) |
| Póker de Leduc | 2 | ✓ | ✓ | | Dos rondas, carta pública; benchmark estándar de CFR |
| Dudo / *Liar's dice* | 2–4 | ✓ | ✓ | | Dados ocultos, pujas crecientes, desafío; usa `std.dice` |
| **Mentiroso** (*Bullshit*) | 3–6 | ✓ | ✓ | ✓ | Bolsas, parámetros de acción ocultos (`subsets`), **ventana de reacción** "¡Mentiroso!", `reveal`. Adelantado desde la ola 2: ya está en IR |

Desde la Fase 4 todos se juegan en el navegador con la [UI genérica](cliente-web.md) (cada paquete
lleva sus pistas `ui { … }`), y el tres en raya, Conecta 4 y Dudo tienen además **UI propia**
(`games/<juego>/ui`).

## Ola 2 — Los juegos que pediste (Fase 6)

| Juego | Jug. | Az | Oc | Si | Qué pone a prueba |
|---|---|:-:|:-:|:-:|---|
| **Parchís** | 2–4 (parejas) | ✓ | | | Tablero como **grafo**, casillas seguras, barreras, capturas (+20), llegada (+10), tres seises, movimientos encadenados |
| **Wizard** | 3–6 | ✓ | ✓ | | **Bazas** (`std.tricktaking`), apuestas, triunfo, magos/bufones, rondas variables |
| **Solitario** (Klondike) | 1 | ✓ | ✓ | | Un jugador (POMDP), muchas acciones, búsqueda/solvers, % de partidas ganables |
| **Ajedrez** | 2 | | | | Legalidad compleja (jaque, enroque, al paso, promoción), **historial** (triple repetición, 50 jugadas), validación por **perft**, rendimiento |
| **Póker** Texas Hold'em No-Limit | 2–10 | ✓ | ✓ | | Rondas de apuestas, **botes secundarios**, evaluador de manos (plugin nativo), acciones con importe |
| **Skat** | 3 (4 con repartidor) | ✓ | ✓ | | **Subasta** (*Reizen*), skat, tipos de juego (palo, Grand, Null, Hand, Ouvert), puntuación compleja |

Bibliotecas que salen de esta ola: `std.cards` (French52, Spanish40/48, Skat32, Wizard60),
`std.dice`, `std.boards` (rejillas con direcciones/rayos, grafos), `std.tricktaking`,
`std.bidding`, `std.betting` (botes y botes secundarios), `std.poker` (evaluador).

## Ola 3 — Sugerencias para ampliar el motor (después)

| Juego | Por qué es interesante |
|---|---|
| **Hanabi** | Cooperativo con información "invertida": ves las cartas de todos **menos las tuyas** (`@visible(all - owner)`) |
| **Mus**, Brisca, Tute, Chinchón | Baraja española; Mus añade **señas** (comunicación limitada entre compañeros) |
| Memory (Parejas) | Juego de memoria → política de *recuerdo* de los bots |
| Dobble / Snap / Jungle Speed | Juegos de **velocidad** → nodos `race` con marca de tiempo del servidor |
| Backgammon | Azar + información perfecta; cubo de doblaje |
| Go 9×9 | Regla del *ko* (historial), puntuación por área |
| Damas | Capturas obligatorias, multi-salto como acción compuesta |
| Stratego, Hundir la flota | Identidades ocultas; **preparación simultánea secreta** |
| UNO | Ventana "¡UNO!" con penalización |
| Blackjack | Jugador contra la banca (política fija de la banca) |
| Diplomacy, Codenames, Catan | Órdenes simultáneas, comunicación y negociación |
| Ultimátum, Ciempiés, Bienes públicos, Concurso de belleza (p-guess) | Clásicos de teoría de juegos/economía experimental, parametrizables |

## Supuestos sobre reglas (a confirmar)

- **Mentiroso** (confirmado 2026-10-09): es el *Bullshit*. Se ponen cartas boca abajo en el centro
  declarando "3 cuatros"; si te acusan y era mentira, te llevas todo el montón; si era verdad, se
  lo lleva quien acusó. Pendiente de confirmar ([pregunta 9b](preguntas-abiertas.md)): secuencia
  de rangos, quién puede acusar, quién sigue tras una acusación y baraja. Dudo queda como la
  versión de dados.
- **Solitario:** Klondike (robo de 1 y de 3 como parámetro). FreeCell sería de información perfecta.
- **Póker:** Texas Hold'em No-Limit; Kuhn y Leduc como versiones mínimas para análisis.
- **Skat:** reglas oficiales internacionales (ISkO).
- **Parchís:** reglas españolas habituales, con variante por parejas.
- **Wizard:** reglas estándar de Amigo; variantes como `params`.

## Definición de "juego terminado" en el catálogo

1. Reglas en `.game` con `meta` completa y reglamento autogenerado revisado.
2. Tests de escenarios que cubren cada regla especial (y *perft* o equivalente si existe).
3. 10⁵ playouts aleatorios sin errores de regla; invariantes declarados.
4. Jugable en la UI genérica; UI propia opcional.
5. Bot de referencia (como mínimo aleatorio + uno heurístico).
6. Ficha de análisis: clasificación, tamaño estimado y lo que se haya podido calcular.
