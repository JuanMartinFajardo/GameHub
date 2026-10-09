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
s.information_state(1)                                     # clave de su conjunto de información
s.snapshot(), s.digest()                                   # configuración canónica y su huella
s.illegal_reason(1, Action.of("call"))                     # por qué no es legal (o None)
s.evaluate(["len", ["var", "moves"]])                      # una expresión de la IR (tests, herramientas)
s.edited([["assign", ["var", "turn"], ["const", 1]]])      # copia editada fuera del flow (los `set` de los tests)
```

`evaluate`, `edited` e `illegal_reason` (Fase 2) sirven a `gamehub test` y a las herramientas; no
forman parte de las reglas ni de las trazas de conformidad. Un juego también se carga desde Nomos:
`gamehub.lang.compiler.load_nomos(Path("games/nim/nim.game"))`.

```bash
gamehub play  JUEGO.game|JUEGO.ir.json --seats human,random [--param k=v] [--save-replay x.ghr.json]
gamehub fuzz  JUEGO.game|JUEGO.ir.json --games 100000 [--players n] [--failures DIR]
gamehub replay PARTIDA.ghr.json [--seat n]
gamehub conformance --check | --write
```

Desde Python también: `gamehub.engine.match` (`play_match`, `RandomAgent`, `fuzz`),
`gamehub.engine.replay` (`record`, `replay`) y la API [`gamehub.build`](#8-api-builder).

## 2. Módulos

| Módulo | Responsabilidad |
|---|---|
| `values` | Valores inmutables, orden canónico total (`sort_key`), tipos de la IR, JSON |
| `rng` | PCG32, sorteos, reproducción y enumeración exacta del azar |
| `expr` | Los 87 operadores de expresión (un test exige cubrir todo el catálogo) |
| `stmt` | Las 14 sentencias, lvalues, selectores y eventos |
| `visibility` | Políticas de visibilidad y redacción de valores |
| `game` | IR → `GameDef` compilado; parámetros y estado inicial; `Game` |
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
  su vector de prueba). Flujos: azar de la partida = 1; agente del asiento *s* = 1000 + *s*.
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
  paso y resultado. La re-simulación comprueba hash y huellas.
- **Trazas de conformidad**: replays con semillas fijas en `spec/conformance/<juego>/`.

## 10. Rendimiento (Python, Apple Silicon)

| Juego | Partidas aleatorias/s | Pasos medios |
|---|---:|---:|
| Dilema del prisionero / PPT | ≈ 12 000 | 2 |
| Póker de Kuhn | ≈ 4 600 | 3,3 |
| Nim (3, 5, 7) | ≈ 2 800 | 6,7 |
| Tres en raya | ≈ 1 600 | 7,6 |
| Mentiroso (3 jugadores) | ≈ 0,9 (2,9 ms por paso) | ≈ 390 |

El cuello de botella de Mentiroso es enumerar los subconjuntos de la mano (hasta 4 047 acciones
por turno) para que el agente aleatorio elija uniformemente. Un perfil mostró que la mitad del
tiempo se iba en deduplicar subconjuntos que ya eran distintos; corregido (×1,8). El motor C++
(Fase 8) está pensado para multiplicar estas cifras.

## 11. Limitaciones conocidas

- Sin comprobación estática de **tipos** (llega con el compilador de Nomos, Fase 2): los errores de
  tipo aparecen al ejecutar como `RuleError`.
- `rank` de los terminales se valida pero aún no se expone; sin rasgos de historial (triple
  repetición) ni tiempo/plazos (IR v0.2).
- Tableros solo de **rejilla**; los grafos (Parchís) llegan en la Fase 6.
- `information_state` recorre todo el historial (coste cuadrático si se llama en cada paso).
