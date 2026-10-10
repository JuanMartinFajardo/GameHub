# Preguntas abiertas

> Decisiones que te corresponden. Cada una lleva mi **recomendación por defecto**: si no dices
> nada, se avanza con ella. 🔴 = bloquea la fase indicada.

| # | Pregunta | Recomendación por defecto | Afecta a |
|---|---|---|---|
| 18 | ¿Apruebas las decisiones de la Fase 3 (**ADR-036 a 043**: Starlette en vez de FastAPI, núcleo de salas puro, actualizaciones y turno vigente, observador público, azar verificable, abandonos, LAN con mDNS y QR, bots en red con la interfaz de siempre) y la fusión de la rama `f3/servidor-partidas` a `main`? | Aprobarlas y fusionar | F4 |
| 19 | ¿Cuándo añadimos el **`on_timeout` de cada juego** (IR v0.2: la jugada por defecto al vencer el plazo, p. ej. «pasar» o «perder la partida» en ajedrez)? Hoy lo decide la sala (`random`, `pass`, `bot`, `forfeit`). | Cuando lo pida un juego del catálogo (ajedrez o Skat, F6) | F6 |
| 20 | ¿Necesitas jugar **por internet** (fuera de la LAN) antes del hub? | Hasta F10, `gamehub serve` en una máquina accesible o un túnel tipo Tailscale; relay propio con el hub (F10) | F4, F10 |
| 3b | ¿Habrá repo remoto en GitHub (u otro host)? | Cuando quieras; el CI ya está preparado | Todo |
| 6 | ¿Quién usará el editor visual? ¿Debe poder diseñar un juego alguien que no programa (bloques tipo Scratch para las condiciones)? | Fase 5: expresiones escritas en los nodos con autocompletado; bloques visuales como mejora posterior | F5 |
| 7 | ¿Te parece bien TypeScript + React para la web? ¿Tienes experiencia con algún framework? | TS + React + React Flow + Monaco | F4–F5 |
| 8 | ¿Quieres un SDK de **Godot** pronto para hacer UIs de juegos ahí? | Después de TS y Python (F6), salvo que te interese antes | F4–F6 |
| 9 | Reglas concretas pendientes: **Solitario** (¿Klondike?), **Póker** (¿Hold'em No-Limit?), **Skat** (¿reglas ISkO?), **Parchís** (¿españolas? ¿parejas?), **Wizard** (¿Amigo estándar?) | Los supuestos del [catálogo](catalogo-de-juegos.md) | F6 |
| 9b | Variantes de **Mentiroso**: ¿el rango sigue la secuencia As, Dos, Tres…, lo elige quien abre ronda o es libre en cada jugada? ¿Puede acusar cualquiera o solo el siguiente? ¿Quién juega tras una acusación? ¿Baraja francesa o española? | Secuencia As→K; acusa cualquiera; sigue el siguiente jugador; francesa de 52. Con Nomos, cada variante es un `extends` de pocas líneas (la española, con `std.cards`) | Mentiroso (cuando quieras) |
| 10 | ¿Trabajas solo? ¿Cuántas horas por semana? ¿Fecha objetivo para el MVP? | Solo + IA; ritmo a definir | Orden y tamaño de fases |
| 11 | ¿Juegos en tiempo real continuo (tipo arcade) o basta con discreto + nodos `race`? | Discreto + `race`; continuo fuera de alcance | Modelo |
| 12 | Plataformas: ¿solo macOS o también Linux/Windows? | Desarrollo en macOS; CI en Linux. El servidor y el cliente de F3 son portables (sin señales Unix obligatorias, entrada en un hilo) pero **no se han probado en Windows**: añadirlo al CI cuando haya repo remoto (3b) | F0, F8 |
| 13 | ¿Pagos numéricos exactos (racionales) o coma flotante? | Racionales en la IR y en el motor de referencia; `double` en el core C++ | F1 |
| 14 | Hosting del hub (¿servidor propio, nube, presupuesto?) | Decidir en F10; todo funciona en local antes | F10 |
| 15 | ¿Guardar estadísticas de partidas humanas para la analítica de balance? (privacidad) | Desde F3 el servidor guarda los replays solo en local (SQLite, con nombres de jugador); usarlos para analítica: opcional y anónimo, activado por el anfitrión | F9 |

## Respondidas

| Fecha | # | Pregunta | Respuesta |
|---|---|---|---|
| 2026-10-09 | 1 | Mensaje cortado en *"También quiero tener una…"* | No lo recuerdas. Cerrada; se reabrirá si aparece. |
| 2026-10-09 | 2 | Licencia | Aceptada la propuesta: Apache-2.0 (motor/SDKs), AGPL-3.0 (servidor del hub), CC-BY-4.0 (juegos). → [ADR-016](decisiones.md), [`LICENSING.md`](../../LICENSING.md) |
| 2026-10-09 | 3 (parcial) | ¿Inicializo git? | Sí: repositorio creado en la rama `main`. Queda pendiente la política de commits (pregunta 3). |
| 2026-10-09 | 4 | Nombre del lenguaje | **Nomos**. → [ADR-017](decisiones.md) |
| 2026-10-09 | 5 | Sintaxis | Llaves y palabras clave en inglés. → [ADR-018](decisiones.md) |
| 2026-10-09 | 9 (parcial) | ¿Qué es "Mentiroso"? | El **Bullshit**: se ponen cartas boca abajo en el centro declarando "3 cuatros"; si te acusan y era mentira, te llevas todo el montón; si era verdad, se lo lleva quien acusó. → [catálogo](catalogo-de-juegos.md), [`mentiroso.ir.json`](../../spec/ir/examples/mentiroso.ir.json) |
| 2026-10-09 | — | ¿Arrancar la Fase 0? | Sí. |
| 2026-10-09 | 3 | Política de commits | **Un commit por tarea.** La Fase 0 va a `main`; cada fase siguiente se trabaja en su rama (`f1/…`) y se fusiona con tu visto bueno. |
| 2026-10-09 | 16 | ¿Aceptadas las ADR propuestas? | Sin objeciones: pediste arrancar la Fase 1 sobre ellas. Se consideran aceptadas (reversibles si cambias de idea). |
| 2026-10-09 | — | ¿Arrancar la Fase 1? | Sí. |
| 2026-10-09 | — | ¿Fusionar la Fase 1 y arrancar la Fase 2? | Sí: F1 fusionada a `main` y F2 en la rama `f2/compilador-nomos`. |
| 2026-10-10 | 17 | ¿Apruebas las ADR-027 a 035 de la Fase 2 y fusionas la rama `f2/compilador-nomos`? | Sí: ADR-027 a 035 aceptadas, F2 fusionada a `main` y F3 en la rama `f3/servidor-partidas`. |
