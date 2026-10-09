# Especificaciones de GameHub

Contratos formales que todos los componentes (Python, C++, web) deben cumplir.

| Ruta | Contenido |
|---|---|
| `ir/v0/ops.json` | **Catálogo de operadores** de la GameIR (expresiones, sentencias, selectores): fuente única de verdad |
| `ir/v0/ir.schema.json` | Esquema del documento completo (juego, estado, funciones, flow, nodos, acciones) |
| `ir/v0/common.schema.json`, `type.schema.json` | Identificadores, textos, visibilidad, bloques y tipos |
| `ir/v0/expr.schema.json`, `stmt.schema.json` | **Generados** desde `ops.json` (`gamehub ir schemas --write`); no editar a mano |
| `ir/examples/*.ir.json` | Juegos de validación escritos a mano: tres en raya, dilema del prisionero, piedra-papel-tijera, Nim, póker de Kuhn, Mentiroso |
| `protocol/` | Protocolo de partidas (Fase 3) |
| `conformance/<juego>/seed-<n>.ghr.json` | **Trazas doradas**: partidas con semilla fija y la huella del estado en cada paso; todo motor debe reproducirlas (`gamehub conformance --check`) |

Validar: `cd python && uv run gamehub ir check ../spec/ir/examples/*.ir.json`

El JSON Schema comprueba la **forma**; `gamehub ir check` añade comprobaciones de **buena
formación** (referencias, contextos, azar solo en nodos `chance`, sin recursión, salidas de nodos).
La semántica está en [`docs/wiki/modelo-formal.md`](../docs/wiki/modelo-formal.md) y la IR en
[`docs/wiki/ir.md`](../docs/wiki/ir.md).

Los `$id` usan el dominio reservado `gamehub.invalid` (RFC 2606): son identificadores, no URLs.
