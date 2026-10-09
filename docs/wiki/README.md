# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-09 |
| **Fase actual** | F1 completada (rama `f1/motor-referencia`, pendiente de fusionar a `main`) → siguiente: F2 (lenguaje Nomos) |
| **Progreso global** | ≈ 13 % (F0 y F1 completas) |
| **Qué funciona** | Motor de referencia en Python que ejecuta cualquier juego en GameIR: azar reproducible (PCG32) y enumerable, información oculta, nodos simultáneos, ventanas de reacción y fases. Se juega en la terminal (`gamehub play`) a 6 juegos, contra personas o bots. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, 6 juegos, trazas de conformidad) · [`python/`](../../python) (`gamehub`: validación, motor, builder, CLI; 132 tests) |
| **Calidad** | 10⁵ partidas aleatorias sin errores en los juegos pequeños; replays verificados paso a paso |
| **Decisiones recientes** | PCG32 normativo (ADR-022), sin pydantic (023), orden de `$exit` (024), hash insensible a valores por defecto (025), ramas por fase (026) |
| **Pendiente de ti** | Fusionar la rama de F1 a `main`; variantes de Mentiroso y el resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | F2: compilador de Nomos (`.game` → IR) con comprobación de tipos, formateador y stdlib v0 |

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
- [Motor de referencia](motor.md) — semántica operacional exacta, azar, eventos, formatos, rendimiento
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
