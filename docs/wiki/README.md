# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-11 |
| **Fase actual** | F5 en curso (rama `f5/studio`): el Studio, editor visual. F0 a F4 están en `main` |
| **Progreso global** | ≈ 41 % (F0 a F4 completas) |
| **Qué funciona** | Se diseñan juegos escribiendo **Nomos** (`.game`): compilador a GameIR con tipos y errores claros, avisos, clasificación, tests e invariantes, formateador, módulos y biblioteca estándar, variantes y combinadores, paquetes, diagrama, reglamento, diff semántico y extensión de VS Code; con **pistas de presentación** (`ui { … }`). **Se juega en red** (servidor de partidas con protocolo WebSocket v1, salas con código, enlace y QR, LAN con mDNS, espectadores, bots, relojes, reconexión, revancha, azar verificable, partidas en SQLite) y ahora **en el navegador**: `gamehub serve` sirve una app web (también en el móvil) donde cualquier juego se juega con la **UI genérica**, sin escribir interfaz, o con una **UI propia** (`gamehub ui new`, tipos por juego con `gamehub sdk ts`; ejemplos: tres en raya, Conecta 4 y Dudo); replays paso a paso, partidas en un mismo dispositivo, español e inglés. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, protocolo v1, trazas) · [`python/`](../../python) (`gamehub`: lenguaje, análisis, motor, servidor, cliente, CLI; 673 tests) · [`web/`](../../web) (SDK TypeScript, UI kit, UI genérica, app para jugar; 85 tests con los de las UIs propias) · [`stdlib/`](../../stdlib/std) · [`games/`](../../games) (15 paquetes, 16 juegos, 3 UIs propias) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Calidad** | Los 16 juegos pasan sus tests e invariantes; los 15 del catálogo se juegan enteros con la UI genérica contra el servidor (test que solo pulsa la interfaz); partida entre el navegador y la terminal (test de aceptación); aceptación de F3 en la LAN; 100 salas simultáneas sin fallos |
| **Decisiones recientes** | Aceptadas (2026-10-11) las de F4, ADR-044 a 051: workspace de pnpm en la raíz (TypeScript 7, React 19, Vite, Biome), tipos del protocolo generados una vez, el servidor sirve la app, pistas `ui` fuera del hash, UI genérica guiada por tipos y dominios, partidas locales contra el servidor, UIs propias en `games/<juego>/ui`, sin librerías de estado ni de idiomas |
| **Pendiente de ti** | El resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | F5: el Studio, editor visual bidireccional (diagrama ↔ texto) con simulador — **MVP de diseño** |

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
- [Cliente web](cliente-web.md) — jugar en el navegador: la app, la UI genérica, el kit, las UIs propias y su plantilla

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
