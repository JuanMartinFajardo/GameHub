# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-09 |
| **Fase actual** | F0 completada → siguiente: F1 (motor de referencia en Python) |
| **Progreso global** | ≈ 4 % (F0: 9 de 9 entregables) |
| **Código** | [`spec/ir/v0`](../../spec/ir/v0): IR núcleo (esquemas + catálogo de operadores) · [`spec/ir/examples`](../../spec/ir/examples): tres en raya, dilema del prisionero, Kuhn y Mentiroso · [`python/`](../../python): paquete `gamehub` con `gamehub ir check` y `gamehub ir schemas` (35 tests) |
| **Diseño** | Visión, modelo formal v0.1, Nomos (RFC v0.1 aprobado), IR, arquitectura, protocolo, Studio, hub, análisis e IA |
| **Decisiones recientes** | Licencias (ADR-016), Nomos (ADR-017), sintaxis (ADR-018), visibilidad sin identidades ocultas (ADR-019), catálogo de operadores (ADR-020) |
| **Pendiente de ti** | Variantes de Mentiroso y el resto de [preguntas abiertas](preguntas-abiertas.md) (ninguna bloquea la F1) |
| **Siguiente paso** | F1: intérprete de la IR (expresiones, efectos, flow, azar con semilla, vistas por jugador) hasta jugar las 4 IR en terminal |

Historial detallado: [`log.md`](../../log.md). Prototipo original: [`structure.py`](../../structure.py) ([análisis](analisis-structure-py.md)).

## Mapa de la wiki

**Visión y diseño**
- [Visión](vision.md) — qué es GameHub, principios, no-objetivos, arte previo
- [Brainstorming: huecos, mejoras e ideas](ideas-y-mejoras.md)
- [Análisis de `structure.py`](analisis-structure-py.md) — qué se conserva y qué cambia

**Especificaciones**
- [Modelo formal](modelo-formal.md) — la semántica: nodos, acciones, azar, información, tiempo, pagos
- [Nomos, el lenguaje `.game`](lenguaje-game.md) — sintaxis con ejemplos (tres en raya, dilema del prisionero, Kuhn, Mentiroso)
- [GameIR](ir.md) — representación intermedia canónica, hashes, versionado, validación ([`spec/`](../../spec/README.md))
- [Protocolo de partidas](protocolo.md) — salas, códigos, mensajes, LAN/online, azar verificable

**Componentes**
- [Arquitectura](arquitectura.md) — monorepo, contrato de motor, pila tecnológica, calidad, seguridad
- [Studio (editor visual)](studio-editor-visual.md)
- [Hub ("GitHub para juegos")](hub.md)
- [Teoría de juegos](teoria-de-juegos.md)
- [Heurísticas, bots, arena e IA](heuristicas-e-ia.md)
- [Catálogo de juegos](catalogo-de-juegos.md)

**Planificación y referencia**
- [Roadmap 0 → 100 %](roadmap.md)
- [Registro de decisiones (ADR)](decisiones.md)
- [Preguntas abiertas](preguntas-abiertas.md)
- [Glosario](glosario.md)

## Cómo se mantiene esta wiki

- Cada sesión de trabajo añade una entrada en `log.md` y actualiza el **Estado del proyecto**.
- Los checkboxes del [roadmap](roadmap.md) son la fuente del % de progreso.
- Toda decisión de arquitectura se registra en [decisiones](decisiones.md).
- Cuando una pregunta abierta se responde, se mueve a "Respondidas" con fecha.
- Las páginas de diseño llevan su estado en la cabecera (borrador → estable → implementado).
