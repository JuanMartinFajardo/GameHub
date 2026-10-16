# Wiki de GameHub

> Plataforma y protocolo para **diseñar juegos con precisión matemática**, versionarlos como en
> GitHub, jugarlos desde cualquier interfaz y estudiarlos con teoría de juegos, heurísticas e IA.

## Estado del proyecto

| | |
|---|---|
| **Última actualización** | 2026-10-16 |
| **Fase actual** | F0 a F6 completas y en `main` (la F6, catálogo ola 2, fusionada el 2026-10-16) → siguiente: documentación en inglés y F7 |
| **Progreso global** | ≈ 59 % (F0 a F6 completas) |
| **Qué funciona** | Se diseñan juegos escribiendo **Nomos** (`.game`) —compilador a GameIR con tipos y errores claros, avisos, clasificación, tests e invariantes, formateador, módulos y biblioteca estándar, variantes y combinadores, paquetes, diagrama, reglamento, diff semántico, pistas de presentación— o **en el Studio** (`gamehub studio`): diagrama y texto sincronizados, inspector, servidor de lenguaje y simulador. **Se juega en red** (salas con código, enlace y QR, LAN, espectadores, bots, relojes, reconexión, azar verificable) y **en el navegador**. El catálogo ya tiene los juegos pedidos: **ajedrez** (FIDE, *perft(5)* exacto), **Skat** (ISkO), **Texas Hold'em** sin límite con botes secundarios, **Wizard**, **Parchís** (también por parejas), **Solitario** Klondike y Mentiroso. El motor guarda los resultados de las funciones puras y compila la IR a código de Python; las funciones caras pueden tener un **plugin nativo** en WebAssembly (el evaluador de póquer), con el cuerpo en Nomos como referencia. |
| **Código** | [`spec/`](../../spec/README.md) (IR v0, protocolo v1, trazas) · [`python/`](../../python) (`gamehub`: lenguaje, LSP, análisis, motor, plugins nativos, servidor, Studio, cliente, CLI; 966 tests, 6 de ellos largos) · [`web/`](../../web) (SDK TypeScript, UI kit, UI genérica, app para jugar, Studio; 136 tests con los de las UIs propias) · [`stdlib/`](../../stdlib/std) (9 módulos) · [`games/`](../../games) (22 paquetes, 23 juegos, 7 UIs propias) · [`editors/vscode/nomos`](../../editors/vscode/nomos) |
| **Calidad** | Aceptación de F6: *perft(5)* del ajedrez = 4 865 609 y los *perft* de referencia de otras cinco posiciones; los valores de juego del Skat cuadran con los ejemplos de la ISkO; 10⁵ partidas al azar sin un error de ajedrez, Skat, Wizard y Parchís (las del Solitario y el Hold'em, en marcha al fusionar); los 22 paquetes del catálogo se juegan enteros con la UI genérica contra el servidor. El evaluador nativo de póquer da lo mismo que la referencia en miles de manos al azar, y el código generado, lo mismo que los cierres en todos los juegos |
| **Decisiones recientes** | Aceptadas (2026-10-16) las de F6, ADR-060 a 066: memo de funciones de la IR; `perft` y `fuzz --jobs`; **plugins nativos en WebAssembly** con referencia obligatoria; código de Python generado desde la IR; bibliotecas de cartas sin genéricos; reglas de la ola 2; ajustes del lenguaje |
| **Pendiente de ti** | El resto de [preguntas abiertas](preguntas-abiertas.md) |
| **Siguiente paso** | Pasar la documentación al inglés; después, F7: teoría de juegos v1 |

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
