# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-09 |
| **Fase actual** | F2 completada (rama `f2/compilador-nomos`, pendiente de fusionar a `main`) → siguiente: F3 (servidor de partidas y protocolo) |
| **Progreso global** | ≈ 24 % (F0, F1 y F2 completas) |
| **Qué funciona** | Se diseñan juegos escribiendo **Nomos** (`.game`): compilador a GameIR con tipos y errores claros, avisos (alcanzabilidad, exhaustividad, fugas de información…), clasificación, tests e invariantes (`gamehub test`), formateador, módulos y biblioteca estándar, variantes (`extends`) y combinadores (`repeat`, `best_of`), paquetes con dependencias, diagrama (`viz`), reglamento (`rules`), diff semántico y extensión de VS Code. Se juegan en la terminal con el motor de F1. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, trazas) · [`python/`](../../python) (`gamehub`: lenguaje, análisis, motor, CLI; 500 tests) · [`stdlib/`](../../stdlib/std) · [`games/`](../../games) (16 juegos) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Calidad** | Los 16 juegos pasan sus tests e invariantes (también en partidas aleatorias); los 6 de F1 compilan con el mismo hash que su IR escrita a mano |
| **Decisiones recientes** | Propuestas de F2, ADR-027 a 035: parser a mano, sin ocultar globales, azúcar por tipos, tests fuera de la IR, módulos, mods y combinadores, paquetes, análisis sobre la IR, formato canónico |
| **Pendiente de ti** | Revisar y fusionar la rama de F2 a `main` (y con ella las ADR-027 a 035); variantes de Mentiroso y el resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | F3: servidor de partidas (salas, protocolo por WebSocket, LAN), para jugar en red |

Historial detallado: [`log.md`](../../log.md). Prototipo original: [`structure.py`](../../structure.py) ([análisis](analisis-structure-py.md)).

## Mapa de la wiki

**Visión y diseño**
- [Visión](vision.md) — qué es GameHub, principios, no-objetivos, arte previo
- [Brainstorming: huecos, mejoras e ideas](ideas-y-mejoras.md)
- [Análisis de `structure.py`](analisis-structure-py.md) — qué se conserva y qué cambia

**Especificaciones**
- [Modelo formal](modelo-formal.md) — la semántica: nodos, acciones, azar, información, tiempo, pagos
- [Nomos, el lenguaje `.game`](lenguaje-game.md) — referencia v0.1: sintaxis, tipos, flow, tests, módulos, mods, herramientas, diagnósticos
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
