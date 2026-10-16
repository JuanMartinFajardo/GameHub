# Motor de referencia (Python)

> Estado: **implementado** (Fase 1, 2026-10-09) en [`python/src/gamehub/engine`](../../python/src/gamehub/engine).
> Este documento fija la **semántica operacional exacta**: cualquier otro motor (C++, WASM) debe
> reproducir las [trazas de conformidad](../../spec/conformance) bit a bit.

## 1. Uso

```python
from gamehub.engine import load_game, Action, Pcg32

game = load_game("spec/ir/examples/kuhn-poker.ir.json")   # valida y compila la IR
s = game.new_state(num_players=2, params={})               # estado inicial (inmutable)
s.status                                                   # CHANCE | DECISION | TERMINAL
s.chance_outcomes()                                        # [((2, 1), Fraction(1, 6)), …]
s = s.apply_chance(s.sample_chance(Pcg32(seed=7)))         # o un resultado concreto
s.active_seats, s.legal_actions(0)                         # (0,), [check, bet]
s.options(0), s.options(0, "bet", {})                      # construcción progresiva
s = s.apply_action(0, Action.of("bet"))                    # devuelve un estado NUEVO
s.view(1), s.events(1)                                     # lo que ve el asiento 1
s.view(PUBLIC), s.events(PUBLIC)                           # lo que ve un espectador (F3)
s.information_state(1)                                     # clave de su conjunto de información
s.snapshot(), s.digest()                                   # configuración canónica y su huella
s.illegal_reason(1, Action.of("call"))                     # por qué no es legal (o None)
s.evaluate(["len", ["var", "moves"]])                      # una expresión de la IR (tests, herramientas)
s.edited([["assign", ["var", "turn"], ["const", 1]]])      # copia editada fuera del flow (los `set` de los tests)
s.iter_legal_actions(0)                                    # las acciones legales de una en una (F3)
s.ranking()                                                # puesto de cada asiento al terminar (F3)
game.decode_action(s.node, {"name": "bet", "args": {}})    # acción desde JSON sin el estado (F3)
```

`evaluate`, `edited` e `illegal_reason` (Fase 2) sirven a `gamehub test` y a las herramientas; no
forman parte de las reglas ni de las trazas de conformidad. `PUBLIC`, `iter_legal_actions`,
`ranking` y `Game.decode_action` (Fase 3) los usan el servidor de partidas y los clientes. Para el
simulador del Studio (Fase 5), `s.outcome_probability(resultado)` da la probabilidad de un
resultado de azar concreto, y cada transición sabe quién es (`TransitionDef.key`:
`("node", "Move", "0")` o `("action", "Bid", "dudo", "1")`): con una lista en
`gamehub.engine.state.TRACE` (un `ContextVar`), el motor apunta las que recorre, lo que da las
flechas del último paso y la cobertura de reglas. Ninguna de las dos cambia la semántica ni las
trazas de conformidad. Un juego también se carga desde Nomos:
`gamehub.lang.compiler.load_nomos(Path("games/nim/nim.game"))`.

```bash
gamehub play  JUEGO.game|JUEGO.ir.json --seats human,random [--param k=v] [--save-replay x.ghr.json]
gamehub fuzz  JUEGO.game|JUEGO.ir.json --games 100000 [--players n] [--failures DIR] [--jobs 6]
gamehub perft JUEGO.game --depth 5 [--divide] [--skip claim_draw] [--jobs 6]
gamehub natives list | check [--trials N] | build --check|--write
gamehub replay PARTIDA.ghr.json [--seat n]                 # también comprueba el azar verificable
gamehub conformance --check | --write
```

`fuzz --jobs N` reparte las partidas entre N procesos (semillas `seed + i`, el mismo informe que
en uno) y `perft` cuenta las secuencias de jugadas legales hasta una profundidad: los puntos de
azar suman las de todos sus resultados, `--skip` deja fuera acciones como reclamar tablas y
`--divide` separa por primera jugada (`gamehub.analysis.perft`, ADR-061).

Desde Python también: `gamehub.engine.match` (`play_match`, `RandomAgent`, `fuzz`, `fuzz_parallel`),
`gamehub.engine.replay` (`record`, `replay`) y la API [`gamehub.build`](#8-api-builder).

## 2. Módulos

| Módulo | Responsabilidad |
|---|---|
| `values` | Valores inmutables, orden canónico total (`sort_key`), tipos de la IR, JSON |
| `rng` | PCG32, sorteos, reproducción y enumeración exacta del azar |
| `expr` | Los 87 operadores de expresión (un test exige cubrir todo el catálogo) |
| `stmt` | Las 14 sentencias, lvalues, selectores y eventos |
| `visibility` | Políticas de visibilidad y redacción de valores |
| `game` | IR → `GameDef` compilado; parámetros y estado inicial; memo de funciones; `Game` |
| `codegen` | Expresiones y funciones de la IR → código fuente de Python (F6, ADR-063) |
| `natives` | Plugins nativos en WebAssembly: búsqueda, carga, ABI y comparación con la referencia (F6, ADR-062) |
| `state` | `State` inmutable y la semántica del flow (`_Tx`) |
| `match`, `replay`, `conformance` | Drivers, agentes, fuzzer, replays y trazas doradas |

## 3. Valores

| Tipo IR | Valor | JSON (vistas, eventos, acciones) |
|---|---|---|
| `Bool`, `Int`, `Seat`, `Text` | bool, int, int, str | nativo |
| `Real` | entero o `Fraction` exacta | entero, o `"n/d"` |
| `Cell`, `tuple`, `list`, `per_player` | tupla | array |
| enum | `EnumValue` | su nombre |
| struct | `StructValue` (campos en orden de declaración) | objeto |
| `option` | valor o `None` | valor o `null` |
| `set` / `map` | ordenados canónicamente | array / array de pares |
| `zone` / `bag` | `Zone(ordered=True/False)`; elementos con `face_up` | `{"size": n, "items": […]}` |
| `grid` | `Grid` (filas × columnas) | array de filas |

**Orden canónico** (`sort_key`): `null` < booleanos < números < textos < enums (por tipo y orden de
declaración) < tuplas (lexicográfico) < structs < conjuntos < mapas < zonas < rejillas. Los
conjuntos, bolsas y claves de mapas se recorren **siempre** en este orden, así que la ejecución no
depende del hash de Python.

## 4. Azar

- **RNG:** PCG32 (XSH-RR 64/32), idéntico a `pcg32_srandom_r(seed, stream)` /
  `pcg32_random_r` / `pcg32_boundedrand_r` de la implementación de referencia en C (verificado con
  su vector de prueba). Flujos: azar de la partida = 1; decisiones del servidor de partidas (la
  jugada aleatoria al vencer un plazo) = 2; agente del asiento *s* = 1000 + *s*.
- **Sorteos por sentencia:** `roll(n)` → `uniform(n) + 1`; `random_choice(xs)` →
  `uniform(len(xs))` sobre el orden canónico; `shuffle` → Fisher–Yates desde el final
  (*i* = n−1 … 1, *j* = `uniform(i+1)`); `sample(dist)` → con denominador común *D* de las
  probabilidades, *r* = `uniform(D)` y el primer índice cuya suma acumulada supera *r*.
- **Resultado** de un punto de azar = tupla de sorteos consumidos por sus efectos. `chance_outcomes`
  los enumera por re-ejecución, en orden lexicográfico, con probabilidad exacta (límite por defecto:
  100 000 resultados → `NotEnumerable`). Ejemplos: Kuhn = 6 resultados de 1/6; barajar 52 cartas
  no es enumerable.
- La preparación (`flow.setup`) con sentencias aleatorias es el primer punto de azar (`node = None`).

## 5. Semántica del flow

1. **Avance hasta quiescencia.** Tras cada paso, el motor recorre nodos `auto`, entradas y salidas de
   fases y transiciones hasta llegar a una decisión, un punto de azar o un terminal. Los saltos se
   encadenan en un bucle (sin recursión); más de **10 000 llegadas** en un paso = `RuleError` (bucle
   sin progreso). Cada llegada emite un evento público `node`.
2. **Transiciones.** Se prueban por grupos y, dentro de cada grupo, en orden de declaración; gana la
   primera cuya guarda es cierta (o no tiene guarda). Grupos: tras una acción de decisión, primero
   las de la **acción** (con `actor` y argumentos) y luego las del **nodo** (con `actor`); en
   ventanas, las del nodo sin `actor`; en el resto, las del nodo. Ninguna aplicable = `RuleError`.
3. **Fases.** Al saltar a un nodo se sale de las fases activas que no lo contienen (`on_exit`, de
   dentro afuera) y se entra en las que sí (`on_enter`, de fuera adentro); entrar en una fase lleva
   a su `start` (recursivamente). Saltar a una fase antecesora la **reinicia**.
   **`$exit`**: se ejecuta `on_exit` de la fase **y después** se evalúan sus transiciones (así
   pueden depender de lo calculado al salir, p. ej. la puntuación de la ronda).
4. **`decision`.** `actor` se evalúa al llegar. Si no tiene ninguna acción legal = `RuleError`.
5. **`simultaneous`.** Actores (sin repetir, por asiento) evaluados al llegar. Los envíos quedan
   ocultos (evento público `submitted`); al completarse, se aplican los efectos **en orden de
   asiento**, luego `resolve`, luego las transiciones del nodo. Sin transiciones por acción.
6. **`window`.** `order` = los elegibles en el orden dado y después el resto de elegibles. Pasar
   (`pass`) es implícito y reservado.
   - `priority`: solo el primero que no ha respondido puede actuar; el primer no-pass se aplica.
   - `collect`: todos responden en secreto (evento `responded`); al completarse, evento
     `responses` con lo que eligió cada uno y se aplica el primer no-pass según `order`.
   - `race`: todos pueden actuar; el primer no-pass que llega se aplica de inmediato.
   - Si todos pasan, transiciones del nodo. Sin elegibles, la ventana se cierra al llegar.
7. **`terminal`.** El pago debe tener exactamente un valor numérico por asiento.

## 6. Acciones

- **Enumeración** (`legal_actions`): acciones en orden de declaración; parámetros en orden; valores
  en el orden del dominio (que puede depender de los parámetros anteriores); se filtra por
  `requires`. En ventanas se añade `pass` al final.
- **Legalidad y forma canónica** (`apply_action`): cada argumento debe pertenecer a su dominio y
  `requires` debe cumplirse. Los dominios `subsets`, `range` y `enum_values` se comprueban sin
  enumerar; los argumentos de `subsets` se reordenan canónicamente (jugar {6♦, 6♥} o {6♥, 6♦} es
  la misma acción).
- **Construcción progresiva** (`options`): nombres disponibles, o valores del siguiente parámetro
  que admiten al menos una acción legal completa.

## 7. Información

- **Vistas** (`view(asiento)`): `{node, status, active, state, responded?, payoffs?}` con cada variable
  redactada según su política (ADR-019): oculto = `{"$hidden": true}`; zonas ordenadas con huecos por
  posición; bolsas con solo los visibles y el tamaño. `view(None)` es omnisciente.
- **Eventos** del último paso (`events(asiento)`), resueltos por asiento al emitirse:

| Tipo | Contenido | Quién lo ve |
|---|---|---|
| `node` | nodo al que se llega | todos |
| `action` | asiento, nombre, argumentos | el actor completo; los demás según la visibilidad de la acción y de cada parámetro (oculto, o solo `{"size"}`) |
| `submitted` / `responded` | asiento que ya eligió | todos |
| `responses` | respuesta de cada asiento en una ventana `collect` | todos |
| `move` | origen, destino, número, valores | cada valor, si era visible en el origen **antes** o en el destino **después**; el evento, si se ve el tamaño de alguna de las dos zonas |
| `flip`, `shuffle` | zona | todos |
| `reveal` | valor y etiqueta | los asientos indicados |
| `emit` | nombre y campos | según su visibilidad (`owner` = actor) |
| `reward` | asiento y cantidad | todos |
| `end` | pagos | todos |

- **Observador público** (`PUBLIC`, Fase 3): lo que ve un espectador, que no ocupa ningún asiento.
  Las políticas se evalúan con un `viewer` que no coincide con ningún `owner`: `owner` nunca le
  deja ver, `all` sí, y un predicado que no se puede evaluar sin asiento (`team[viewer] == …`)
  cuenta como falso. Así `@visible(viewer != owner)` (Hanabi) sí le muestra las cartas. De los
  eventos ve los públicos, lo que se revela **a todos** los asientos, las acciones según su
  visibilidad para quien no es el actor y los movimientos según la visibilidad de las zonas.
- **Puesto final** (`ranking`): 1 = primero y los empates comparten puesto; sale del `rank` del
  nodo terminal si lo declara y, si no, de los pagos (más pago, mejor puesto).
- **Estado de información** (`information_state`): SHA-256 de la secuencia de (vista, eventos) de
  ese asiento en todos los estados desde el inicio: recuerdo perfecto. Dos historias son
  indistinguibles para un asiento si y solo si su clave coincide (verificado en Kuhn).

## 8. API builder

`gamehub.build` construye la IR desde Python (`Expr` con operadores, `GameBuilder`, `T.*`,
sentencias). Tres juegos reconstruidos con ella dan **el mismo hash de reglas** que sus JSON
escritos a mano (`tests/test_build.py`).

## 9. Formatos

- **Instantánea** (`snapshot`): JSON canónico con `node`, `store` (zonas como `{items, face_up}`),
  `pending` y `payoffs`. **Huella** (`digest`) = SHA-256 de la instantánea.
- **Replay** `gamehub-replay/0.1` (`.ghr.json`): juego (id, versión, hash de reglas), jugadores,
  parámetros, semilla, pasos (`{"chance": [sorteos]}` o `{"seat", "action"}`), huella tras cada
  paso y resultado. La re-simulación comprueba hash y huellas. Campos opcionales del servidor de
  partidas (F3): `players` (nombre y tipo de cada asiento), `fairness` (azar verificable) y, en
  `result`, `ranking`, `reason` (`terminal`, `forfeit`, `aborted`) y `forfeited`; una partida que
  no llega a un terminal no tiene `payoffs`. `replay.frames(juego, datos, asiento)` da cada
  estado de la partida con su vista y los eventos que llevaron a él tal como los vio un asiento,
  un espectador o con todo a la vista (el visor de replays de la app web, F4).
- **Azar verificable** (`gamehub.engine.fairness`, esquema `gamehub-fair/1`): el servidor publica
  `SHA-256("gamehub-fair/1:commit:" + server_seed)` antes de la partida; la semilla de la partida
  es SHA-256 del JSON canónico `{scheme, server_seed, client_seeds}` (primeros 8 bytes, 53 bits);
  al terminar se revela `server_seed`. `gamehub replay` comprueba el compromiso, la semilla y que
  cada resultado de azar sea el que da PCG32 con ella.
- **Trazas de conformidad**: replays con semillas fijas en `spec/conformance/<juego>/`.

## 10. Rendimiento (Python, Apple Silicon)

Ninguna de estas técnicas cambia la semántica: las trazas de conformidad son las mismas y un test
comprueba que, en todos los juegos del catálogo, las partidas al azar dan la misma huella en cada
paso con y sin ellas.

### Memo de funciones

`GameDef` clasifica cada función de la IR por lo que lee (análisis estático transitivo,
`_memo_kinds`, ADR-060):

- **static** (solo sus argumentos: ni estado, ni opciones, ni asientos, ni contexto): su resultado
  se guarda para todas las partidas del juego (`GameDef.static_memo`, hasta 200 000 entradas).
  Así las tablas del ajedrez (rayos, saltos de caballo) o el valor de una mano de póquer se
  calculan una vez.
- **state** (estado y opciones, pero no el nodo en curso ni los asientos de contexto): se guarda en
  `State.memo`; cada escritura en el almacén de una transacción lo vacía, así que no hay
  invalidación que olvidar.
- Sin memo: las que dependen del contexto (`actor`, `owner`, `viewer`…) y las que no tienen
  bucles ni llamadas (guardarlas costaría más que calcularlas).

### Código generado

`gamehub.engine.codegen` escribe cada expresión y cada función de la IR como código fuente de
Python (un `def` por función con sus argumentos y locales como variables; `let` y las
comprensiones como lambdas) y lo compila con `exec` (ADR-063). Llama a las mismas funciones de
cada operador que los cierres de `expr`, así que da los mismos resultados y los mismos errores;
los enteros tienen atajos (`add`, `lt`, `cell`…) que no pasan por los racionales. Los cierres
siguen siendo la referencia: se usan si algo no se puede generar, con `GAMEHUB_CODEGEN=0` o con
`Game(ir, codegen=False)`. Un test exige que el generador cubra todo el catálogo de operadores.

### Plugins nativos

Una función con `"native": "modulo.funcion"` ([IR](ir.md), `@native` en
[Nomos](lenguaje-game.md#plugins-nativos)) se puede sustituir por un plugin que dé exactamente el
mismo resultado; **su cuerpo es la implementación de referencia** (ADR-062). Los plugins son
módulos **WebAssembly sin importaciones** (el mismo binario valdrá en el navegador y en el core
C++), con un límite de cómputo por llamada (50 millones de unidades de combustible de
`wasmtime`). ABI `gamehub-native/1`:

- El módulo exporta `memory`, `gh_buffer() -> i32` (un búfer de al menos 64 KiB) y una función
  por cada función nativa: `(in: i32, len: i32, out: i32) -> i32`.
- Los argumentos van al búfer como palabras i32 en orden: `Bool` 0/1, `Int` y `Seat` tal cual,
  `Cell` como fila y columna, un enumerado por su ordinal, un struct campo a campo, una tupla
  elemento a elemento, una lista como su longitud y sus elementos, un opcional como 0 o como 1 y
  el valor. La función escribe el resultado igual a partir de `out` y devuelve cuántas palabras
  escribió (negativo = error).
- El plugin del módulo `a.b` es `a.b.wasm` (o su fuente `a.b.wat`) en un directorio de
  `GAMEHUB_NATIVE_PATH` o en `stdlib/std/native/`. `natives.register(id, impl)` registra una
  implementación en Python (para tests o programas de confianza).
- En Python hace falta `wasmtime` (extra `gamehub[wasm]`); sin él, con `GAMEHUB_NATIVES=0` o si
  un entero no cabe en i32, se usa la referencia. `gamehub natives check` compara plugin y
  referencia con entradas al azar (0 diferencias en `std.poker.hand_value`) y `natives build
  --check` (en el CI) comprueba que cada `.wasm` es su `.wat` compilado.

### Cifras

Partidas al azar por segundo con un proceso (antes de F6):

| Juego | Partidas aleatorias/s | Pasos medios |
|---|---:|---:|
| Dilema del prisionero / PPT | ≈ 12 000 | 2 |
| Póker de Kuhn | ≈ 4 600 | 3,3 |
| Nim (3, 5, 7) | ≈ 2 800 | 6,7 |
| Tres en raya | ≈ 1 600 | 7,6 |
| Mentiroso (3 jugadores) | ≈ 0,9 (2,9 ms por paso) | ≈ 390 |

El cuello de botella de Mentiroso es enumerar los subconjuntos de la mano (hasta 4 047 acciones
por turno) para que el agente aleatorio elija uniformemente. Un perfil mostró que la mitad del
tiempo se iba en deduplicar subconjuntos que ya eran distintos; corregido (×1,8).

Los juegos de F6, en la aceptación de 10⁵ partidas (`fuzz --jobs 6`, 8 núcleos):

| Juego | Partidas/s | Pasos medios |
|---|---:|---:|
| Ajedrez | 11 | 346 |
| Skat (3 / 4 jugadores) | 117 / 83 | 120 / 160 |
| Wizard (3 / 6 jugadores) | 20 / 38 | 711 / 401 |
| Parchís (2 / 4 jugadores) | 57 / 25 | 351 / 665 |

*Perft* del ajedrez: el memo y la reescritura de las reglas (líneas de jaque y clavadas, el rey en
el estado, las tablas de `std.boards`) bajaron el *perft(3)* de 52 s a 1,2 s, y el *perft(5)*
(4 865 609 posiciones) tardó 131 s con 6 procesos; el código generado llegó después (×2).
El motor C++ (Fase 8) está pensado para multiplicar estas cifras.

## 11. Limitaciones conocidas

- La IR escrita a mano no se comprueba por **tipos** (Nomos sí, desde la Fase 2): sus errores de
  tipo aparecen al ejecutar como `RuleError`.
- Sin rasgos de historial ni tiempo en la IR (v0.2): el ajedrez guarda en su estado las posiciones
  para las repeticiones, y los plazos los pone la sala.
- Una llamada a un plugin WebAssembly cuesta ~25 µs en Python: solo compensa en funciones caras
  (el evaluador de póquer gana ×3).
- `information_state` recorre todo el historial (coste cuadrático si se llama en cada paso).
