# Brainstorming: huecos, mejoras e ideas

> Resultado de la sesión de diseño del 2026-10-09. Cada idea enlaza a la página donde se desarrolla.

## A. Huecos de la idea original (detalles imprescindibles que faltaban)

| # | Hueco | Propuesta | Dónde |
|---|---|---|---|
| 1 | **Pagos y resultados** | Vector de pagos en terminales + ranking + recompensas intermedias para RL | [Modelo §3.8](modelo-formal.md) |
| 2 | **Azar** | Pseudo-jugador *naturaleza*; solo en nodos `chance`; distribuciones explícitas; enumerable vs. muestreable | [Modelo §3.3](modelo-formal.md) |
| 3 | **Información fina** | Visibilidad por *ubicación* (variable, zona, tamaño, componente, evento) y dependiente del estado | [Modelo §3.4](modelo-formal.md) |
| 4 | **Fugas de información sutiles** | Handles opacos, re-anonimizar al barajar, orden canónico, aviso si la legalidad depende de datos ocultos | [Modelo §3.4](modelo-formal.md) |
| 5 | **Asiento ≠ participante** | Las reglas hablan de asientos; humanos/bots/espectadores los ocupan | [Protocolo §2](protocolo.md) |
| 6 | **Simultaneidad real e interrupciones** | Nodos `simultaneous` y `window` (¡Mentiroso!, ¡UNO!, reclamar en Mahjong) | [Modelo §3.5](modelo-formal.md) |
| 7 | **Tiempo** | Relojes, plazos, `on_timeout`; juegos de velocidad con marca de tiempo del servidor | [Protocolo §9](protocolo.md) |
| 8 | **Parámetros y variantes** | `params` con validaciones; nº de jugadores como rango | [Lenguaje](lenguaje-game.md) |
| 9 | **Reglas que dependen del historial** | Rasgos de historial declarados (triple repetición) manteniendo el estado markoviano | [Modelo §3.7](modelo-formal.md) |
| 10 | **Reproducibilidad** | Determinismo total, semillas, replays, notación universal de posición | [Modelo §4](modelo-formal.md) |
| 11 | **Acciones con varios parámetros** | Construcción progresiva (origen → destino → promoción) | [Protocolo §6](protocolo.md) |
| 12 | **Terminación** | Detección estática de bucles sin progreso; `max_steps` | [Modelo §7](modelo-formal.md) |
| 13 | **Tests de reglas** | Bloques `test`, invariantes, fuzzing, trazas doradas | [Arquitectura §5](arquitectura.md) |
| 14 | **¿Qué versión de las reglas?** | Hash de reglas en todo artefacto (bot, replay, análisis, rating) | [IR §5](ir.md) |
| 15 | **Meta-acciones de sala** | Deshacer, ofrecer tablas, pausar, abandonar: fuera de las reglas, en el protocolo (abandonar, implementado en F3; el resto, pendiente) | [Protocolo §9](protocolo.md) |
| 16 | **Seguridad** | Reglas = datos; plugins puros en sandbox; servidor autoritativo | [Arquitectura §6](arquitectura.md) |
| 17 | **Propiedad intelectual** | Reglamentos y arte propios; cuidado con marcas | [Hub §10](hub.md) |

## B. Mejoras propuestas

**Diseño de juegos**
1. **IR canónica con tres frentes**: texto `.game`, diagrama del Studio y API Python *builder*
   (para familias generadas por programa: matrices aleatorias, tableros paramétricos).
2. **Statecharts jerárquicos** en vez de un diagrama plano (partida → ronda → baza → turno).
3. **Combinadores de juegos**: `repeat`, `best_of`, `sum` (suma de CGT), `sequence`, `with_params`.
4. **Mods = herencia + parches** (`extends`, `override`, `remove`): un mod es un diff pequeño y legible.
5. **Biblioteca estándar** de barajas, dados, tableros, bazas, subastas y apuestas.
6. **Reglamento autogenerado** (Markdown/PDF, multi-idioma) a partir de la IR, con diagramas.

**Verificación y análisis**
7. **Análisis de flujo de información**: detector automático de fugas.
8. **Cobertura de reglas** (como la cobertura de código): reglas que nunca se disparan.
9. **Asesor de viabilidad**: clasificación + tamaño estimado + qué cálculos son posibles.
10. **Módulos de CGT y de juegos cooperativos** (Sprague–Grundy, Shapley, núcleo).
11. **Torneos de juegos repetidos** estilo Axelrod.
12. **Puentes a OpenSpiel, Gambit, PettingZoo y CGSuite** desde el principio; importadores de
    notaciones existentes (PGN, SGF…).

**Jugar e interfaces**
13. **UI genérica automática**: cualquier juego es jugable sin escribir interfaz.
14. **UI kit** (cartas, manos, tableros, dados, relojes) + pistas de renderizado opcionales en el `.game`.
15. **SDKs tipados generados por juego** (TS, Python, Godot, Unity).
16. **Azar verificable** (commit–reveal) en partidas online.
17. **Puzzles y posiciones**: empezar desde cualquier estado serializado.
18. **Modo árbitro** para partidas físicas (p. ej. llevar la puntuación del Skat de la mesa real).
19. **Accesibilidad**: como todo es estructurado, la UI genérica puede ser accesible por lector de pantalla.

**Colaboración**
20. **Diff semántico, visual y de comportamiento** (Balance CI) en las propuestas de cambio.
21. **Semver automático** por hash de interfaz.
22. **Árbol genealógico** de juegos (forks/variantes) y **búsqueda por propiedades matemáticas**.
23. **GameHub Pages**: alojamiento de UIs propias.
24. **Modo aula**: ejercicios de teoría de juegos sobre juegos reales.

**IA (al final)**
25. Tensorización automática desde la IR; adaptadores RL; entornos vectorizados en C++.
26. Agentes LLM y diseño asistido (reglas en lenguaje natural → borrador `.game`).
27. Política de *recuerdo* y de tiempo de reacción para bots (juego limpio).

## C. Ideas para más adelante

- **Modo Nomic**: juegos cuyas acciones modifican las propias reglas (parches a la IR en mitad
  de la partida).
- **Diseño evolutivo de juegos**: búsqueda (genética) sobre IRs guiada por las métricas de
  balance, como hizo el sistema *Ludi* de Cameron Browne (que diseñó *Yavalath*).
- **Mental poker**: partidas P2P sin árbitro de confianza.
- **Edición colaborativa en tiempo real** del diagrama (CRDT).

### Surgidas en la Fase 4 (cliente web)

- **Animaciones a partir de los eventos**: los eventos `move`, `flip` y `reveal` ya dicen qué va
  de dónde a dónde; la UI genérica podría animar cartas y fichas sin saber nada del juego.
- **Pistas para más formas**: recorridos (`track`, para el Parchís), grafos con coordenadas,
  dados como forma de elegir un argumento (la cara en Dudo), agrupar variables en paneles.
- **Etiquetas traducibles en la IR**: hoy `meta.tags` son palabras en inglés que la app traduce
  con un diccionario; un catálogo de etiquetas compartido serviría también al hub.
- **App instalable y sin conexión** (PWA) cuando haya motor en el navegador (WASM, F8): partidas
  locales y replays sin servidor.
- **Un tema por juego**: el kit ya se pinta con variables CSS; un juego podría traer su paleta
  (tapete, madera, colores de los asientos) en la sección `ui`.
- **Grabar una partida como vídeo o GIF** desde el visor de replays, para compartirla.

## D. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Alcance enorme | Cortes verticales; MVP jugable en Fase 4 (hecho: cualquier juego del catálogo se juega en el navegador) y de diseño en Fase 5; IA al final |
| Expresividad vs. analizabilidad | Núcleo puro y total + plugins nativos puros como vía de escape |
| Lentitud del intérprete | Escalera de rendimiento: Python → VM C++ → codegen |
| El lenguaje cambia mucho al principio | La IR versionada es la frontera estable; migraciones automáticas |
| Round-trip texto ↔ diagrama | IR de autor + tests de propiedad de idempotencia |
| Errores en información oculta | Handles opacos, análisis de fugas, tests de vistas |
| Divergencia entre motores | Suite de conformidad diferencial con trazas doradas |
| Comunidad vacía al lanzar | Catálogo de clásicos + utilidad completa en local sin comunidad |
| Bots maliciosos | Sandbox con límites de recursos |
