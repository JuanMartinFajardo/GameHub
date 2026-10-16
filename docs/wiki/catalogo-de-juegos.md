# Catálogo de juegos

> Estado: **olas 1 y 2 completas** (Fases 2 y 6, 2026-10-16). Los 22 paquetes (23 juegos) están
> en Nomos en [`games/`](../../games), cada uno con sus tests, y se juegan en la terminal
> (`gamehub play`), en red y en el navegador.
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

| Juego | Paquete | Jug. | Az | Oc | Si | Qué pone a prueba |
|---|---|---|:-:|:-:|:-:|---|
| **Parchís** | [`parchis`](../../games/parchis) | 2–4 (parejas) | ✓ | | | Recorridos con `std.boards`, seguros, barreras, capturas (+20), llegada (+10), tres seises, premios encadenados |
| **Wizard** | [`wizard`](../../games/wizard) | 3–6 | ✓ | ✓ | | Bazas (`std.tricktaking`), apuestas, triunfo, magos y bufones, rondas de 1 a 60/n cartas |
| **Solitario** (Klondike) | [`solitaire`](../../games/solitaire) | 1 | ✓ | ✓ | | Un jugador (POMDP), cartas boca abajo en una lista de zonas, muchas acciones |
| **Ajedrez** | [`chess`](../../games/chess) | 2 | | | | Legalidad completa (jaque, clavadas, enroque, al paso, coronación), historial (repeticiones, 50/75 jugadas), **perft** |
| **Póker** Texas Hold'em sin límite | [`texas-holdem`](../../games/texas-holdem) | 2–10 | ✓ | ✓ | | Rondas de apuestas, subidas mínimas, **botes secundarios** (`std.betting`), evaluador (`std.poker`, plugin nativo) |
| **Skat** | [`skat`](../../games/skat) | 3 (4 con quien reparte descansando) | ✓ | ✓ | | **Subasta** (*Reizen*), skat, palo / Grand / Null, Hand, Schneider, Schwarz, Ouvert, matadores, juego pasado de la subasta |

Mentiroso, el séptimo juego pedido, llegó en la ola 1. El ajedrez, el póker, Wizard y el Parchís
tienen además **UI propia** (`games/<juego>/ui`); el Skat y el Solitario se juegan con la UI
genérica.

Bibliotecas que salieron de esta ola: `std.cards` (también `skat32()` y la baraja de Wizard,
`wizard60()`), `std.boards` (direcciones, rayos y saltos dentro del tablero, recorridos),
`std.tricktaking`, `std.betting` (botes y botes secundarios) y `std.poker` (valor de una mano,
con plugin nativo en WebAssembly).

### Fichas de análisis

Clasificación de `gamehub check` y tamaño del árbol con el estimador de Knuth (60 paseos al azar;
para árboles tan grandes es solo un orden de magnitud). Con agentes al azar.

| Juego | Clasificación | Estados (Knuth) | Pasos medios | Ramificación media |
|---|---|---|---:|---:|
| Ajedrez | 2 jugadores, determinista, información perfecta, suma cero | ~10⁷⁵⁷ | 350 | 21,9 |
| Skat (una mano, 3) | azar, información imperfecta | ~10⁶¹ | 40 | 7,2 |
| Texas Hold'em (una mano, 2 / 6) | azar, información imperfecta | ~10⁷⁹ / ~10⁸¹ | 4,8 / 9,2 | 74 / 34 |
| Wizard (3, partida entera / una ronda) | azar, información imperfecta | ~10²⁰⁵⁰ / ~10⁸⁴ | 711 / 7 | 5,4 / 1,5 |
| Parchís (4) | azar, información perfecta | ~10⁵¹⁷ | 663 | 2,5 |
| Solitario (robo de una) | 1 jugador, azar, información imperfecta | ~10¹¹²⁷ | 1 000 (tope) | 8,1 |

Comprobaciones exactas: **perft(5) = 4 865 609** desde el inicio y los *perft* de Kiwipete y de
las posiciones 3 a 6 de la Chess Programming Wiki; los valores de juego del Skat con los ejemplos
de la ISkO.

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

## Reglas elegidas

- **Mentiroso** (confirmado 2026-10-09): es el *Bullshit*. Se ponen cartas boca abajo en el centro
  declarando "3 cuatros"; si te acusan y era mentira, te llevas todo el montón; si era verdad, se
  lo lleva quien acusó. Pendiente de confirmar ([pregunta 9b](preguntas-abiertas.md)): secuencia
  de rangos, quién puede acusar, quién sigue tras una acusación y baraja. Dudo queda como la
  versión de dados.
- Los de la ola 2, con las recomendaciones de la [pregunta 9](preguntas-abiertas.md)
  ([ADR-065](decisiones.md)):
  - **Ajedrez:** FIDE. Tablas automáticas por ahogado, material insuficiente, quíntuple
    repetición y 75 jugadas; reclamables por triple repetición y 50 jugadas. Rendirse y perder
    por tiempo son cosa del servidor (abandonar, y la opción `forfeit` de la sala).
  - **Skat:** ISkO, sin Kontra ni Ramsch (si pasan todos, la mano no se juega); Seeger-Fabian como
    opción.
  - **Parchís:** reglas españolas; con dos jugadores, colores opuestos; por parejas como opción.
  - **Wizard:** reglas de Amigo; la variante *hook* como opción.
  - **Póquer:** Texas Hold'em sin límite con ciegas fijas; Kuhn y Leduc quedan como versiones
    mínimas para el análisis.
  - **Solitario:** Klondike (robo de una o de tres, vueltas al descarte como opción, tope de
    jugadas). FreeCell sería de información perfecta.

## Definición de "juego terminado" en el catálogo

1. Reglas en `.game` con `meta` completa y reglamento autogenerado revisado.
2. Tests de escenarios que cubren cada regla especial (y *perft* o equivalente si existe).
3. 10⁵ playouts aleatorios sin errores de regla; invariantes declarados.
4. Jugable en la UI genérica; UI propia opcional.
5. Bot de referencia (como mínimo aleatorio + uno heurístico). *Hoy, solo el aleatorio: los bots
   heurísticos llegan con los bloques `heuristic` de la Fase 9.*
6. Ficha de análisis: clasificación, tamaño estimado y lo que se haya podido calcular.
