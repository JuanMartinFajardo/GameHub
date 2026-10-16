# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-16 |
| **Fase actual** | F0 a F5 completas y en `main` (la F5, el Studio, fusionada el 2026-10-16) → siguiente: F6 |
| **Progreso global** | ≈ 51 % (F0 a F5 completas) |
| **Qué funciona** | Se diseñan juegos escribiendo **Nomos** (`.game`) —compilador a GameIR con tipos y errores claros, avisos, clasificación, tests e invariantes, formateador, módulos y biblioteca estándar, variantes y combinadores, paquetes, diagrama, reglamento, diff semántico, pistas de presentación— y ahora también **en el Studio** (`gamehub studio`): diagrama y texto a la vez, sincronizados en los dos sentidos sin perder comentarios, inspector con formularios, diseñador de componentes, plantillas, problemas en vivo, servidor de lenguaje (también `gamehub lsp` para cualquier editor) y un **simulador** con vistas por asiento, viaje en el tiempo, puntos de ruptura, partidas masivas con cobertura de reglas en el diagrama, árbol, comparar versiones y exportar. **Se juega en red** (servidor de partidas, salas con código, enlace y QR, LAN, espectadores, bots, relojes, reconexión, azar verificable) y **en el navegador** con la UI genérica o UIs propias. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, protocolo v1, trazas) · [`python/`](../../python) (`gamehub`: lenguaje, LSP, análisis, motor, servidor, Studio, cliente, CLI; 798 tests) · [`web/`](../../web) (SDK TypeScript, UI kit, UI genérica, app para jugar, Studio; 113 tests con los de las UIs propias) · [`stdlib/`](../../stdlib/std) · [`games/`](../../games) (15 paquetes, 16 juegos, 3 UIs propias) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Calidad** | Aceptación de F5: el tres en raya se crea desde cero solo con el diagrama, pasa sus tests, se juega en el simulador y es el mismo juego que el del catálogo; Dudo se edita en el diagrama sin perder un comentario y el texto llega al diagrama (contra el servidor de verdad, y la app entera manejada en jsdom). Ediciones al azar en todos los juegos conservan los comentarios (Hypothesis). Los 16 juegos pasan sus tests e invariantes; los 15 del catálogo se juegan enteros con la UI genérica |
| **Decisiones recientes** | Aceptadas (2026-10-16) las de F5, ADR-052 a 059: el `.game` es lo que se guarda y el diagrama edita su árbol con reescritura mínima comprobada; LSP con pygls (stdio y WebSocket); **CodeMirror en vez de Monaco**; React Flow + ELK con la disposición en `<juego>.layout.json`; índice de símbolos; seguridad del Studio; simulador en el servidor con traza y estimador de Knuth; tests e invariantes desde el Studio |
| **Pendiente de ti** | El resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | F6: catálogo ola 2 (los 7 juegos pedidos) y biblioteca estándar madura |

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
- [Studio (editor visual)](studio-editor-visual.md) — diseñar con diagrama y texto a la vez, inspector, simulador y herramientas (F5)
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
