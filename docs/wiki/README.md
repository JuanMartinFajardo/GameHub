# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-10 |
| **Fase actual** | F4 en curso (rama `f4/cliente-web`): jugar en el navegador. F0, F1, F2 y F3 están en `main` |
| **Progreso global** | ≈ 32 % (F0, F1, F2 y F3 completas) |
| **Qué funciona** | Se diseñan juegos escribiendo **Nomos** (`.game`): compilador a GameIR con tipos y errores claros, avisos (alcanzabilidad, exhaustividad, fugas de información…), clasificación, tests e invariantes (`gamehub test`), formateador, módulos y biblioteca estándar, variantes (`extends`) y combinadores (`repeat`, `best_of`), paquetes con dependencias, diagrama (`viz`), reglamento (`rules`), diff semántico y extensión de VS Code. **Se juega en red**: `gamehub host` abre una sala en la LAN (código, enlace, QR, mDNS) y los demás entran con `gamehub join`; servidor de partidas con protocolo WebSocket v1 (JSON Schema), espectadores, bots (también por la red, con la misma interfaz `Agent`), relojes, reconexión, revancha, azar verificable y partidas guardadas en SQLite. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, trazas) · [`python/`](../../python) (`gamehub`: lenguaje, análisis, motor, servidor, cliente, CLI; 604 tests) · [`stdlib/`](../../stdlib/std) · [`games/`](../../games) (15 paquetes, 16 juegos) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Calidad** | Los 16 juegos pasan sus tests e invariantes; aceptación de F3 con procesos reales en la LAN (4 personas en Dudo, reconexión, bot por código); 100 salas simultáneas sin fallos |
| **Decisiones recientes** | Aceptadas (2026-10-10) las de F3, ADR-036 a 043: Starlette en vez de FastAPI, núcleo de salas puro, actualizaciones y turno vigente, observador público, azar verificable, abandonos, LAN con mDNS y QR, bots en red con la interfaz de siempre |
| **Pendiente de ti** | El resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | F4: jugar en el navegador (SDK TypeScript, UI genérica a partir de la IR, UI kit, lobby) — **MVP jugable** |

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
- [Protocolo de partidas](protocolo.md) — v1 implementada: salas, mensajes, turnos, espectadores, relojes, LAN, azar verificable, rendimiento

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
