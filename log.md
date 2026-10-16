# Log de trabajo

Registro cronológico de lo que se hace en el proyecto. La entrada más reciente va arriba.
Formato: fecha · qué se hizo · decisiones · pendientes / siguientes pasos.

---

## 2026-10-16 — F5 aprobada y fusionada a `main`

**Respuesta recibida**: «Sí» a la pregunta 22: ADR-052 a 059 aceptadas (entre ellas **CodeMirror en
vez de Monaco**, que cambia la ADR-012) y `f5/studio` fusionada a `main` con `--no-ff`. Nada se ha
subido.

**Siguientes pasos**: F6, catálogo ola 2 (los 7 juegos pedidos) y biblioteca estándar madura, en la
rama `f6/…`.

**Progreso**: ≈ 51 % (F0 a F5 en `main`).

---

## 2026-10-12 — Sesión 7: Fase 5, el Studio

**Respuestas recibidas**: «ve con la fase 5», que se tomó como visto bueno a las ADR-044 a 051 y a
fusionar F4 (hecho, `d14ae62`; nada se ha subido). F5 se trabaja en la rama `f5/studio`.

**Hecho (un commit por tarea)**
- **Núcleo** (`2cde02a`): posición de cada nombre en el árbol, **índice de símbolos** del
  comprobador (declaraciones, usos resueltos y tipos de cada expresión), referencia de lo
  predefinido, fragmentos sueltos con errores situados, el **motor de ediciones** (~45 operaciones
  sobre el árbol con reescritura mínima del texto, comprobada volviendo a analizar) y el **modelo
  del documento** para el diagrama y los formularios. Compilar para el editor se salta el JSON
  Schema (era el 90 % del tiempo).
- **Servidor de lenguaje** (`cff47a3`) con pygls: diagnósticos, autocompletado con el texto a
  medias, hover, definición, referencias, renombrar con comprobación de choques, formato, esquema,
  plegado, firmas y arreglos rápidos; `gamehub lsp` por stdio y el mismo servidor por el WebSocket
  del Studio.
- **Servidor del Studio** (`8c4277e`): `gamehub studio` (API del espacio de trabajo, disposición
  en `<juego>.layout.json`, juegos nuevos desde plantillas, historia de git), seguridad (solo
  local, token, Host y Origin), **simulador** (historia con viaje en el tiempo, correr hasta
  puntos de ruptura, recargar reglas, partidas masivas con cobertura gracias a la traza de
  transiciones del motor, árbol, recuento, tamaño con el estimador de Knuth) y **plantillas**
  (`gamehub new --template`).
- **Tests e invariantes en el Studio** y **aceptación** (`7e62df0`): operaciones para editarlos y
  `gamehub/tests` para ejecutarlos (sin ellas, la plantilla vacía no compilaba en cuanto se tocaba
  su acción); pruebas de aceptación contra el servidor de verdad.
- **El Studio web** (`428b6f4`): `@gamehub/nomos` (Nomos para CodeMirror), `@gamehub/studio`
  (diagrama con React Flow + ELK, editor y campos con CodeMirror y el LSP, inspector, diseñador
  de componentes, simulador con la UI genérica, partidas masivas, árbol, comparar, exportar SVG y
  PNG) y la app; pruebas unitarias, de integración y de la app entera en jsdom.
- **Rueda y CI** (`16d9b6e`): la rueda lleva el Studio compilado; la CI compila las dos apps.
- **Aceptación**: el tres en raya se construye desde la plantilla vacía con 24 gestos del
  diagrama y del inspector, pasa sus tests, se juega en el simulador y es el mismo juego que el
  del catálogo (mismas jugadas legales y pagos en 40 partidas al azar); Dudo se cambia en el
  diagrama (nodo nuevo, flecha reconectada —una línea de texto—, acciones reordenadas, la ronda
  metida en una fase) sin perder ningún comentario, y lo escrito en el texto, también roto y
  arreglado, llega al diagrama. Revisado a mano en el navegador integrado.
- **Fallos encontrados y corregidos al probar en el navegador**: guardar daba siempre conflicto
  (la versión del archivo iba en nanosegundos y no cabe exacta en un número de JavaScript: ahora
  en microsegundos); las flechas tapaban las asas de salida y no se podía tirar otra desde un nodo
  que ya tenía alguna; ELK ponía el nodo de apuestas de Dudo por encima del inicio (rompía el
  ciclo por la flecha equivocada: ahora por el orden del texto); al cambiar de vista el diagrama
  quedaba fuera del encuadre; un nodo nuevo quedaba fuera de la vista; del clic al diagrama
  pasaban más de 0,65 s (el editor esperaba medio segundo para sincronizar el texto y el servidor
  otros 150 ms para analizarlo: ahora ~70 ms); en las partidas masivas un empate contaba como victoria de los dos (69 % + 44 %);
  «Contar» el árbol podía tardar medio minuto sin dar señales (ahora con límite y «Contando…»); el
  generador de dados creaba un nodo de azar sin transición; los selectores de idioma y tema
  ocupaban todo el ancho; «1 avisos»; los tipos de nodo salían en español con la interfaz en
  inglés; dos copias de `@lezer/highlight`; el WebSocket del Studio rechazaba mensajes de más de
  64 KB (un `.game` grande al abrirlo).
- Docs: página del [Studio](docs/wiki/studio-editor-visual.md) reescrita (implementado),
  lenguaje §4 y §13 (`gamehub studio`, `gamehub lsp`, plantillas), arquitectura, motor (traza),
  roadmap, licencias (elkjs es EPL-2.0), READMEs; ADR-052 a 059. Tests: 798 de Python y 113 de la
  parte web.

**Decisiones** (propuestas): ADR-052 a 059; la más visible, **CodeMirror en vez de Monaco**
(ADR-054, cambia la ADR-012): más ligero y pensado para decenas de campos con su cliente LSP.

**Limitaciones**: sin edición colaborativa; sin bloques tipo Scratch (pregunta 6); mover una
acción de un nodo a otro se hace en el texto; la extensión de VS Code aún no usa el LSP; el Studio
necesita el servidor local (sin él, con el WASM de F8 y el hub de F10). El panel del navegador
integrado era pequeño: el diseño de escritorio se comprobó midiendo la página y con capturas a ese
tamaño, no a pantalla completa.

**Pendiente de ti**: revisar las ADR-052 a 059 y dar el visto bueno para fusionar `f5/studio` a
`main` (pregunta 22).

**Siguiente**: F6, catálogo ola 2 (los 7 juegos pedidos) y biblioteca estándar madura.

**Progreso global**: ≈ 51 %.

---

## 2026-10-11 — Fase 4 aprobada y fusionada

- «Ve con la fase 5»: se toman como aprobadas las ADR-044 a 051 y la fusión. La rama
  `f4/cliente-web` se fusiona a `main` y la Fase 5 (el Studio: editor visual bidireccional con
  simulador) arranca en la rama `f5/studio`.
- Pregunta 21 movida a respondidas.
- Progreso global: ≈ 41 %.

---

## 2026-10-11 — Sesión 6: Fase 4, jugar en el navegador

**Respuestas recibidas**: aprobar las ADR-036 a 043, fusionar F3 a `main` (hecho, `0607c1b`) y
arrancar F4 en la rama `f4/cliente-web`.

**Hecho (un commit por tarea)**
- **Monorepo de JavaScript** (ADR-044): workspace de pnpm en la raíz con `web/packages/*`,
  `web/apps/*` y `games/*/ui` (empezó dentro de `web/`; se movió a la raíz porque pnpm no lo
  encontraba al trabajar dentro de una UI de `games/`). Node 22, TypeScript 7 estricto, React 19,
  Vite 8, Biome y Vitest, con versiones exactas en un catálogo; trabajo nuevo en el CI.
- **`@gamehub/protocol`**: los tipos de TypeScript salen del mismo generador que los de Python
  (`gamehub protocol types` escribe y comprueba los dos, ADR-045). En el esquema, `Number`,
  `Event` y `Error` pasan a `ExactNumber`, `GameEvent` y `ErrorInfo` (la red no cambia).
- **`@gamehub/client`**, el SDK de TypeScript: conexión con reconexión y `resume`, latido, ids
  únicos, resync si falta una actualización, fin si otra pestaña toma la sesión; estado inmutable
  con un reductor puro; acciones enumeradas y progresivas; sesiones en localStorage; API REST.
  Probado contra el servidor de Python de verdad (dos clientes, una caída y un espectador).
- **Sección `ui { … }` de Nomos** (ADR-047): pistas de presentación con destino (variables,
  opciones, tipos, acciones y sus parámetros, nodos, asientos) y un catálogo cerrado (cómo y dónde
  dibujar, nombres traducidos, símbolos, colores, cartas, cómo elegir un argumento), comprobadas
  (E701–E704), con formato, descompilador y mezcla en variantes. En la IR, una clave `ui`
  opcional que no cuenta para el hash: las trazas de conformidad no cambian.
- **`@gamehub/ui-kit`** (rejilla accesible, cartas en SVG con palos franceses y españoles, mano en
  abanico, montón, mazo, dados, fichas, recorrido, grafo, jugador, marcador, reloj, barra de
  acciones; variables CSS con tema claro y oscuro) e **`@gamehub/i18n`** (es/en).
- **`@gamehub/auto-ui`, la UI genérica** (ADR-048): el aspecto de cada variable sale de su tipo y
  sus pistas; cómo se elige cada argumento, de su dominio (`cells(G)` → casillas,
  `subsets(items(Z))` → marcar cartas) o de una pista; un constructor de acciones con los valores
  que dan las acciones legales, calculados una vez por actualización. Registro de eventos en
  frases y resultado. Y **`@gamehub/react`** (hooks sobre el SDK).
- **El servidor sirve la app** (ADR-046): `gamehub serve`/`host` (`--open`, `--no-web`); el enlace y
  el QR de cada sala abren la app; QR en SVG y replays estado a estado (`/frames?seat=`). La rueda
  de Python lleva la app compilada (probado instalándola en un entorno limpio).
- **La app para jugar** (`@gamehub/shell` y `web/apps/play`): inicio (código, crear sala, salas
  abiertas, partidas recientes), crear sala (opciones del juego, reloj, espectadores, bots), sala
  (jugador o espectador, sesión guardada al recargar, lobby con código, enlace y QR, asientos,
  bots, configuración, listo, chat, revancha), partida con la UI genérica o una propia, replays
  paso a paso desde cualquier perspectiva, **partidas en un mismo dispositivo** con pantalla de
  privacidad (ADR-049) y galería del kit en `/kit`. Español e inglés, tema claro u oscuro, móvil.
- **Pistas `ui` en los 15 paquetes del catálogo** (nombres en es/en, símbolos, colores, cartas,
  dados, la columna de Conecta 4…).
- **UIs propias** (ADR-050): `gamehub sdk ts` (tipos de un juego, con formato de Biome y
  `--check`) y `gamehub ui new` (plantilla que funciona a la primera: tipos, tablero inicial,
  test, servidor de desarrollo con la app solo para ese juego). Con ella, las UIs del **tres en
  raya** (marcas dibujadas, línea ganadora), **Conecta 4** (fichas que caen, columna resaltada) y
  **Dudo** (apuesta en el tapete, historia de la ronda, cubiletes, última dudada, selector de
  apuesta con dados); la app las registra sola.
- **Aceptación**: los 15 juegos del catálogo se juegan enteros contra el servidor solo pulsando
  la UI genérica (test de integración, al azar con semilla); **Ana en la app contra Luis con
  `gamehub join` en una terminal de verdad**, hasta el final; sala con la app contra un bot y
  modo espectador. Revisado a mano en el navegador integrado, también a tamaño de móvil.
- **Fallos encontrados y corregidos**: el QR salía roto (`svg_inline` no lleva `xmlns` y un
  `<img>` no lo dibuja); los jugadores de los replays venían por posición y no por asiento; el
  registro ponía dobles paréntesis y lo revelado antes que la jugada; Mentiroso tardaba 170 s en
  el test de aceptación (el constructor recalculaba miles de subconjuntos en cada pulsación: ahora
  35 s); el catálogo del servidor incluía el juego de tests del PD iterado (ahora, de cada
  paquete, su archivo principal); en jsdom, el WebSocket del navegador simulado (undici) choca con
  su clase `Event`: los tests usan `ws`.
- Docs: página nueva del [cliente web](docs/wiki/cliente-web.md), lenguaje §12 (`ui`), IR,
  protocolo, arquitectura, glosario, ideas, READMEs (el de la raíz seguía en la Fase 1); ADR-044
  a 051. Tests: 673 de Python y 85 de la parte web (con los de las UIs propias).

**Decisiones** (propuestas): ADR-044 a 051.

**Limitaciones**: sin motor en el navegador, el modo local necesita el servidor que sirve la app
(hasta el WASM de F8); no hay animaciones; lo de «una UI propia en menos de una hora» se apoya en
la plantilla y en las tres UIs de ejemplo, no en una medición con otra persona; Windows sigue sin
probar.

**Pendiente de ti**: revisar las ADR-044 a 051 y dar el visto bueno para fusionar
`f4/cliente-web` a `main` (pregunta 21).

**Siguiente**: F5, el Studio: editor visual bidireccional (diagrama ↔ texto) con simulador, el
**MVP de diseño**.

**Progreso global**: ≈ 41 %.

---

## 2026-10-10 — Fase 3 aprobada y fusionada

- Apruebas las ADR-036 a 043 y la fusión: la rama `f3/servidor-partidas` se fusiona a `main` y la
  Fase 4 (cliente web: SDK TypeScript, UI genérica, UI kit, app para jugar) arranca en la rama
  `f4/cliente-web`.
- Pregunta 18 movida a respondidas.
- Progreso global: ≈ 32 %.

---

## 2026-10-10 — Sesión 5: Fase 3, el servidor de partidas y el juego en red

**Respuestas recibidas**: aprobar las ADR-027 a 035, fusionar F2 a `main` (hecho, `a178967`) y
arrancar F3 en la rama `f3/servidor-partidas`.

**Hecho (un commit por tarea)**
- **Motor**: vista y eventos de un **espectador** (`PUBLIC`, no ocupa asiento; un predicado que no
  se puede evaluar sin asiento cuenta como falso), **puesto final** (`ranking`, del `rank` del
  terminal o de los pagos), acciones legales perezosas y decodificación sin estado.
  **Azar verificable** `gamehub-fair/1` (compromiso, semillas de los jugadores, semilla de 53
  bits, revelación) y `gamehub replay` que lo comprueba. Las trazas de conformidad no cambian.
- **Protocolo v1** en JSON Schema (`spec/protocol/v1`): 15 mensajes del cliente, 11 del servidor y
  la API REST; tipos de Python generados (`gamehub protocol types`, en CI).
- **Servidor de partidas** (Starlette + uvicorn + websockets, ADR-036): núcleo de salas **puro**,
  sin red ni reloj propio (ADR-037), probado con un reloj simulado. Salas con código, asientos
  `open/reserved/human/bot`, anfitrión, configuración; una actualización por entrada con `seq` sin
  huecos y rechazo por **turno vigente** (sin rechazos espurios en nodos simultáneos, ADR-038);
  acciones enumeradas o progresivas; reconexión con token y `resume`; espectadores con vista
  pública u omnisciente y retardo; bots del servidor; relojes `move`/`match` con `on_timeout`;
  **abandonos** (último puesto y un bot termina por el asiento, ADR-041); revancha; anulación si
  las reglas fallan; límites (tasa, tamaños, salas, conexiones) y limpieza de salas vacías.
- **Persistencia** en SQLite: cada paso al jugarse; tras una caída, las partidas a medias se
  cierran como anuladas con su replay verificable. `gamehub serve`.
- **SDK cliente de Python** (reconexión automática, peticiones con respuesta) y **bots en red con
  la misma interfaz `Agent`** que en proceso (ADR-043); `gamehub bot run agente.py --room CÓDIGO`.
- **Juego en la LAN** (ADR-042): `gamehub host juego` (código, enlace `/r/CÓDIGO`, QR en la
  terminal, anuncio mDNS), `gamehub join CÓDIGO|enlace` (busca la sala en la LAN; guarda la
  sesión para volver tras cerrar la terminal), `gamehub rooms`; cliente de terminal con lobby,
  comandos (`/listo`, `/chat`, `/bot`…), menús de jugadas, relojes, resultado y revancha.
- **Rendimiento**: perfilando Mentiroso por red, `to_json` despacha por tipo exacto y la
  enumeración de acciones reutiliza la conversión de cada carta (servidor ×3,7) y el cliente
  decodifica las acciones solo cuando el agente las mira: partida de 3 bots de 52 s a ~5 s.
  **Prueba de carga** (`gamehub loadtest`): 100 salas simultáneas, Dudo a 4 (400 conexiones)
  ≈ 890 jugadas/s y Nim ≈ 1 300/s, sin fallos.
- **Aceptación** con procesos reales en la red local (`tests/test_acceptance_f3.py`,
  `GAMEHUB_LAN_TESTS=1`): cuatro `gamehub join` como cuatro ordenadores juegan Dudo en una sala
  de `gamehub host` (dos la encuentran por mDNS, dos por el enlace); a uno se le cae la terminal en
  su turno y vuelve; en la revancha entra un bot por el código. Cinco de cinco.
- **Fallos encontrados y corregidos**: los ids de mensaje del cliente se repetían entre procesos
  y el servidor descartaba como reintentos las jugadas de quien retomaba la sesión desde otra
  terminal (lo encontró la aceptación); al retomar sin nada pendiente no llegaba ninguna
  actualización y el cliente no sabía que era su turno; un nombre largo dejaba sin respuesta el
  `hello`; la salida de `gamehub host` a una tubería se quedaba en el búfer; los tests escribían
  sesiones en `~/.local/share/gamehub` (ahora, un directorio temporal).
- Docs: `protocolo.md` reescrita (v1 implementada, rendimiento), `motor.md`, `arquitectura.md`,
  `heuristicas-e-ia.md` (interfaz `Agent`), glosario, ADR-036 a 043; 604 tests.

**Decisiones** (propuestas): ADR-036 a 043.

**Pendiente de ti**: revisar las ADR-036 a 043 y dar el visto bueno para fusionar
`f3/servidor-partidas` a `main` (pregunta 18); preguntas nuevas 19 (`on_timeout` por juego) y 20
(jugar por internet antes del hub).

**Siguiente**: F4, el cliente web (SDK TypeScript con tipos generados del mismo esquema, UI
genérica a partir de la IR, UI kit, lobby): el **MVP jugable**.

**Progreso global**: ≈ 32 %.

---

## 2026-10-10 — Fase 2 aprobada y fusionada

- Apruebas las ADR-027 a 035 y la fusión: la rama `f2/compilador-nomos` se fusiona a `main` y la
  Fase 3 (servidor de partidas y protocolo) arranca en la rama `f3/servidor-partidas`.
- Pregunta 17 movida a respondidas. Corregido un recuento de la wiki: son 15 paquetes de juego con
  16 juegos (el paquete del PD iterado trae también su juego de tests).
- Progreso global: ≈ 24 %.

---

## 2026-10-09 — Sesión 4: Fase 2, el lenguaje Nomos y sus herramientas

**Respuestas recibidas**: fusionar F1 a `main` (hecho, `bc6b203`) y arrancar F2 en la rama
`f2/compilador-nomos`.

**Hecho (un commit por tarea)**
- Parser de Nomos escrito a mano (descenso recursivo + precedencias) con recuperación de errores,
  diagnósticos al estilo rustc y comentarios conservados como trivia.
- Formateador canónico `gamehub fmt` (idempotente, conserva comentarios); en CI y pre-commit.
- Comprobador de tipos y traducción a GameIR (`gamehub compile`, `gamehub check`); `play`, `fuzz`
  y `replay` aceptan `.game`. **Los seis juegos de F1 escritos en Nomos (`games/`) compilan con el
  mismo hash de reglas que su IR escrita a mano.**
- Descompilador IR → Nomos (`gamehub decompile`): ida y vuelta exacta en los 6 ejemplos y en un
  juego «fregadero» que usa todas las construcciones (`python/tests/fixtures/kitchen-sink.game`).
- Corregido un fallo del validador de F1: `at(Nodo)` en la visibilidad del estado o en funciones
  se daba por nodo desconocido.
- Formateador, segunda vuelta: las cadenas aritméticas largas rellenan líneas y las de `and`/`or`
  van una por línea; un valor que no cabe tras `=` pasa a la línea siguiente, o se abre junto al
  `=` si empieza por un corchete y tampoco cabe allí; se conservan las líneas en blanco alrededor
  de los comentarios. Fallo latente corregido: el formateador podía partir tras `=`, `requires`,
  `when` o `clave:` y el parser no lo admitía. `fmt --diff` ya no escribe. Test de estrés: todos
  los juegos, formateados a anchos de 24 a 80 columnas, vuelven al mismo árbol sintáctico.
- **`gamehub test`**: ejecuta los bloques `test` (azar resuelto con la semilla del test,
  `chance where` condicionado a la probabilidad, `play` con asiento implícito si solo uno puede
  actuar, `expect`, `expect legal/illegal`, `set`) y comprueba los invariantes en cada estado del
  test y en partidas aleatorias (`--playouts`, 20 por defecto). Los fallos se explican al estilo
  rustc con los valores en juego (`payoff == [1, -1]` es falso: `payoff` vale [2, -2]) y las
  jugadas legales. Errores nuevos: E601/E602 (configuración del test) y E610–E614 (fallos).
  Motor: `State.evaluate`, `State.edited` e `illegal_reason`. Los 19 tests y 4 invariantes de los
  juegos pasan; en CI.
- **Análisis de `gamehub check`** (paquete `gamehub.analysis`, sobre la IR, así que sirven también
  para IR escrita a mano o por el futuro editor visual): nodos inalcanzables (W401), transiciones
  que pueden no cubrir todos los casos (W402, reconoce parejas `c`/`not c`, `a < b`/`a >= b` y
  enums completos), nodos sin camino a un final (W403), bucles de nodos `auto` sin efectos
  (W404), **fugas de información v1** (W405: datos ocultos que llegan a estado o eventos públicos,
  también por un `if`; quién juega o qué nodo sigue según datos ocultos; jugadas legales que
  dependen de lo que el actor no ve), declaraciones sin usar (W406; los usos en tests cuentan) y
  transiciones tapadas en IR a mano (W407). **Clasificación** estática (jugadores, azar,
  información, simultaneidad, suma cero si se puede asegurar). Los avisos se sitúan en el texto
  con un mapa de fuentes. Los seis juegos no dan ningún aviso; el fregadero da los esperables.
  `gamehub test` juega siempre las partidas aleatorias e informa si los pagos suman constante.
- **Módulos e `import`** (`import a.b.{X, Y}`, `import a.b.*`): `std.…` en la biblioteca
  estándar y el resto relativo al archivo; importar un nombre trae lo que necesita, y solo llega
  a la IR lo que el juego usa. Errores: módulo no encontrado (E503), nombre inexistente (E201,
  con sugerencia), importación circular (E504), choques de nombres (E202). Un archivo sin
  juegos es un módulo y `gamehub check` lo comprueba. Las casillas se pueden indexar (`c[0]`
  fila, `c[1]` columna).
- **Biblioteca estándar v0** (`stdlib/std/`): `std.cards` (baraja francesa de 52 y española de
  40/48, `rank_value`, `is_red`…), `std.dice` (caras, recuentos con comodín, escaleras…),
  `std.grid` (direcciones, rayos, distancias) y `std.graph` (grafos como listas de aristas,
  ciclos, vecinos). Probada con tests escritos en Nomos (`tests/fixtures/stdlib.game`).
- **Mods**: `game V extends Base { … }` (la base puede ser del archivo, importada o un
  combinador) con declaraciones nuevas, `override` (fn, tipos, nodos —también dentro de fases—,
  params, state; un `override params` con `assert` sustituye las restricciones), `remove` y
  `extend node` (acciones al final, transiciones delante). Meta mezclado sin `id`/`version`; tests
  e invariantes no se heredan; la base no cambia. Errores E505.
- **Combinadores**: `game G = repeat(Base, rounds: n, payoff: sum|mean)` y
  `best_of(Base, rounds: n)`, como transformaciones de la IR (fase de ronda, terminales que
  apuntan el resultado, nodo «Siguiente», terminal final; `rounds` pasa a ser un parámetro; nombres
  nuevos sin choques). Errores E506. Un combinador se puede extender (se descompila), p. ej. para
  añadirle tests. Probado: PD iterado (9/9 cooperando, media 3 y 4/3), al mejor de 3 (suma cero),
  variantes del tres en raya (inverso, con pase, 4×4).
- En un `import`, `prisoners_dilemma` encuentra también `prisoners-dilemma.game`.
- **Paquetes** (`gamehub.packages`): `game.toml` (nombre, versión, archivo principal, licencia,
  autores, `forked_from`, `[dependencies]` por `path` o `git` + `rev`), `game.lock` con el commit
  de cada dependencia git (también las transitivas) y caché en `~/.cache/gamehub/git`. Los
  `import` buscan en `std`, después en las dependencias del paquete y después junto al archivo.
  Comandos: `gamehub new` (paquete con un juego mínimo que compila y pasa su test: una carrera
  hasta la meta), `fetch [--update]`, `clone` y `fork` (anota `forked_from` con el commit y deja
  el remoto original como `upstream`). Los seis juegos de `games/` ya son paquetes. Probado con
  repositorios git locales (sin red).
- **`gamehub viz`** (Mermaid o Graphviz): cada nodo con su forma según el tipo, quién juega, sus
  acciones y el pago; flechas con la acción y la condición en Nomos; las fases como subgrafos con
  marcas de entrada y salida. Comprobado renderizando los diagramas con Mermaid en el navegador.
- **`gamehub rules`**: reglamento en Markdown generado de la IR (clasificación, opciones,
  componentes, qué hay en la mesa y quién lo ve, el diagrama, cada nodo con sus acciones,
  condiciones y efectos en Nomos, definiciones), en el idioma pedido.
- **`gamehub diff A B`** o **`gamehub diff REV1..REV2 archivo`**: diff semántico por elementos
  (no por líneas), en texto o JSON, que dice si cambian las reglas o solo los textos.
- **Extensión de VS Code** (`editors/vscode/nomos`, JavaScript sin compilación): gramática
  TextMate, configuración del lenguaje, diagnósticos de `gamehub check --format json` al abrir y
  guardar (también en módulos importados) y formato con `gamehub fmt --stdin` (nuevo). Un test
  comprueba que la gramática cubre todas las palabras reservadas y funciones del lenguaje.
  Corregido: un juego sin `flow` daba un error sin posición (ahora uno solo, en el juego).
- **Juegos nuevos en Nomos**, cada uno un paquete con tests (64 comprobaciones en total, todas
  en verde, sin avisos):
  - **Conecta 4** (tablero y línea parametrizables; invariante: las fichas no flotan);
  - **familia 2×2**: base `two-by-two` (dos tablas de pagos como opciones) y las variantes
    **caza del ciervo**, **gallina**, **pares o nones** y **batalla de los sexos** con `extends`
    (`override enum` para renombrar las opciones, `override params` para los pagos);
  - **dilema del prisionero iterado** con `repeat(PrisonersDilemma, rounds: 10)` y un
    `tests.game` que lo extiende;
  - **póker de Leduc** (dos rondas, límite de subidas, carta común);
  - **Dudo** de 2 a 4 jugadores, que usa `std.dice`.
- Mejoras que salieron al escribirlos: el análisis de fugas entiende `reveal … to all`; las
  funciones de módulo tienen su propio ámbito (sus parámetros pueden llamarse como cosas del
  juego); la recuperación de errores del parser respeta los corchetes anidados (un error dentro
  de un texto ya no cierra el bloque y lo arrastra todo); los textos traducibles admiten saltos
  de línea entre idiomas.

- **Documentación**: `lenguaje-game.md` reescrita como referencia de Nomos v0.1 (léxico,
  módulos y paquetes, tipos, visibilidad, expresiones, efectos y flow, tests, mods, herramientas,
  traducción a la IR, diagnósticos, formato y diferencias con el RFC); ADR-027 a 035; estado,
  arquitectura, IR, motor, glosario, catálogo y preguntas abiertas al día.
- `spec/` y `stdlib/` viajan dentro de la rueda de Python: probado instalándola en un entorno
  aislado, fuera del repositorio (Dudo, que importa `std.dice`, compila y pasa sus tests).

**Decisiones (propuestas, ADR-027 a 035)**: parser a mano en vez de Lark; ningún local oculta un
global salvo en funciones de módulo; azúcar guiado por los tipos con traducción en una pasada;
tests e invariantes fuera de la IR; módulos con poda y resolución std → dependencias →
relativa; mods sobre el modelo y combinadores sobre la IR; paquetes con `game.toml` y `game.lock`;
análisis estáticos sobre la IR; formato canónico al estilo Prettier.

**Aceptación de la Fase 2** ✅
- Los 16 juegos de la ola 1 están en `.game` y pasan sus tests: `gamehub test ../games` da 64
  comprobaciones en verde (tests, invariantes y partidas aleatorias) y `gamehub check`, ningún
  aviso. Los 6 de F1 compilan con el mismo hash de reglas que su IR escrita a mano.
- `fmt` idempotente y estable a cualquier ancho (todos los juegos, de 24 a 100 columnas).
- `texto → IR → texto` estable: ida y vuelta exacta con el descompilador.
- `viz`: una caja por nodo y una flecha por transición en todos los juegos (test).
- 500 tests de Python; `ruff`, `pyright`, `gamehub ir check` y las trazas de conformidad en verde.

**Pendiente de ti**: revisar las ADR-027 a 035 y dar el visto bueno para fusionar
`f2/compilador-nomos` a `main` (pregunta 17); variantes de Mentiroso (9b).

**Siguientes pasos**: Fase 3, servidor de partidas (salas con código, protocolo WebSocket + JSON
con JSON Schema, proyección por asiento, reconexión, LAN) para jugar en red desde la terminal.

**Progreso:** ≈ 24 % (F0, F1 y F2 completas).

---

## 2026-10-09 — Sesión 3: Fase 1, motor de referencia en Python

**Respuestas recibidas**
- Commits: uno por tarea. → Fase 0 en `main` (3 commits); Fase 1 en la rama `f1/motor-referencia`
  (un commit por tarea), pendiente de fusionar con el visto bueno del usuario (ADR-026).
- Arrancar la Fase 1: sí. Las ADR propuestas se consideran aceptadas (sin objeciones).

**Qué se hizo**
- `gamehub.ir.hashing`: hash de reglas (JSON canónico + SHA-256), insensible a `meta`, `doc` y
  valores por defecto (ADR-025). Validación: `pass` reservado en ventanas, sin transiciones por
  acción en nodos simultáneos, fases de las que se sale con `$exit` con transiciones.
- **Motor de referencia** (`gamehub.engine`):
  - valores inmutables con orden canónico; tipos; JSON;
  - **PCG32** idéntico a la implementación de referencia en C (vector de prueba verificado),
    sorteos reproducibles y **enumeración exacta** de resultados de azar (ADR-022);
  - los 87 operadores y las 14 sentencias del catálogo, compilados a funciones;
  - semántica del flow: decisiones, simultáneos, ventanas (priority/collect/race), azar, fases con
    `on_enter`/`on_exit`/`$exit` (ADR-024), avance hasta quiescencia sin recursión;
  - visibilidad: vistas redactadas, eventos resueltos por asiento, estados de información con
    recuerdo perfecto (verificado: en Kuhn el asiento 1 no distingue KQ de JQ);
  - acciones legales, forma canónica y construcción progresiva (`options`);
  - instantánea y huella del estado; replays `.ghr.json` verificados paso a paso.
- Drivers: `play_match`, `RandomAgent`, `fuzz`; **trazas doradas** en `spec/conformance` (6 juegos).
- **API builder** (`gamehub.build`): tres juegos reconstruidos con ella dan el mismo hash de reglas
  que sus JSON escritos a mano.
- **CLI**: `gamehub play` (hot-seat y bots, pantalla de cambio de jugador), `fuzz`, `replay`,
  `conformance`.
- Juegos nuevos: **piedra-papel-tijera** y **Nim** (con variante misère).
- Docs: `docs/wiki/motor.md` (semántica operacional exacta), ADR-022 a 026, roadmap, arquitectura,
  glosario, README.
- 132 tests; `ruff` y `pyright` limpios.
- Perfilado de Mentiroso: la mitad del tiempo era deduplicar subconjuntos ya distintos; corregido (×1,8) sin cambiar las trazas de conformidad.

**Aceptación de la Fase 1**

| Juego | Partidas aleatorias | Errores | Partidas/s | Comprobación |
|---|---:|---:|---:|---|
| Tres en raya | 100 000 | 0 | 1 579 | Pago medio de X +0,294 (teórico +0,297) |
| Dilema del prisionero | 100 000 | 0 | 11 972 | Pago medio 2,249 (exacto 9/4) |
| Piedra, papel o tijera | 100 000 | 0 | 11 790 | Pago medio −0,003 (exacto 0) |
| Nim (3, 5, 7) | 100 000 | 0 | 2 805 | — |
| Póker de Kuhn | 100 000 | 0 | 4 600 | Pago medio +0,133 (exacto 1/8) |
| Mentiroso (3 jugadores) | 1 000 | 0 | 0,4 (≈ 0,9 tras optimizar) | 391 pasos de media; gana un 31,6 / 32,2 / 36,2 % por asiento: el asiento 0 recibe 18 cartas y los demás 17 |

Además: valor exacto del juego aleatorio calculado sobre el árbol completo (Kuhn = 1/8, dilema = 9/4,
PPT = 0); replays idénticos bit a bit; vistas sin fugas; partida completa jugable en la terminal.

**Decisiones**: ADR-022 (PCG32), 023 (sin pydantic), 024 (orden de `$exit`), 025 (hash), 026 (ramas).

**Pendiente / siguientes pasos**
- Del usuario: fusionar `f1/motor-referencia` en `main`; variantes de Mentiroso (pregunta 9b).
- F2: compilador de Nomos (`.game` → IR) con tipos, formateador, stdlib v0 y paquetes.

**Progreso:** ≈ 13 % (F0 y F1 completas).

---

## 2026-10-09 — Sesión 2: respuestas del usuario y Fase 0 completada

**Respuestas recibidas**
- Mensaje cortado ("También quiero tener una…"): no lo recuerda → pregunta cerrada.
- Licencias propuestas: aceptadas (ADR-016).
- Mentiroso = *Bullshit*: cartas boca abajo con un *claim* ("3 cuatros"); si te acusan y era
  mentira, te llevas el montón; si era verdad, se lo lleva quien acusó.
- Nombre **Nomos** y palabras clave en inglés: aceptados (ADR-017, ADR-018).
- Inicializar git y arrancar la Fase 0: sí.

**Qué se hizo**
- `git init -b main` (sin commits: política de commits pendiente). `.gitignore`, `.editorconfig`,
  `LICENSE` (texto canónico de Apache-2.0, md5 verificado), `LICENSING.md`.
- **Especificación de la IR núcleo v0.1** en `spec/ir/v0/`:
  - `ops.json`: catálogo de 87 expresiones, 14 sentencias y 6 selectores (aridad, tipos de
    argumento, aleatoriedad, documentación). Fuente única de verdad (ADR-020).
  - `ir.schema.json`, `common.schema.json`, `type.schema.json` (a mano) y `expr.schema.json`,
    `stmt.schema.json` (generados desde el catálogo).
- **Juegos de validación** en `spec/ir/examples/`: tres en raya, dilema del prisionero (con
  restricciones T > R > P > S), póker de Kuhn y **Mentiroso** (adelantado desde la ola 2).
- **Paquete Python `gamehub`** (`python/`, gestionado con `uv`): validación por JSON Schema +
  comprobador de buena formación (referencias, contextos, azar confinado, sin recursión,
  salidas de nodos), CLI `gamehub ir check` y `gamehub ir schemas --check|--write`.
- 35 tests (20 casos de error deliberados); `ruff`, `pyright` (0 errores) y formato en verde.
- CI de GitHub Actions y hooks de `pre-commit` locales.
- Mejora del modelo de información (ADR-019): se descartan los *handles* opacos (filtraban qué
  carta jugaba un rival) en favor de zonas ordenadas con posiciones públicas y **bolsas** sin
  orden; las componentes ocultas no exponen identidad; `reveal` es un evento.
- Wiki actualizada: preguntas, decisiones (ADR-016 a 021), modelo formal, Nomos (Mentiroso
  completo), IR (validación), protocolo, catálogo, roadmap, glosario, arquitectura, estado.

**Decisiones**
- Aceptadas: ADR-016 (licencias), 017 (Nomos), 018 (sintaxis).
- Propuestas e implementadas: ADR-019 (visibilidad), 020 (catálogo), 021 (IR de autor en F2).

**Pendiente / siguientes pasos**
- Del usuario: política de commits, variantes de Mentiroso (pregunta 9b), visto bueno a las ADR.
- F1: intérprete de la IR en Python (expresiones, efectos, flow, azar con semilla, vistas
  redactadas, replays) hasta jugar las 4 IR en terminal.

**Progreso:** ≈ 4 % (F0: 9/9).

---

## 2026-10-09 — Sesión 1: brainstorming, diseño y roadmap

**Contexto de partida**
- El repo solo contenía `structure.py` (prototipo de mayo 2026: `GameState` singleton, `Node`,
  `Action`, `Flowchart`, permisos por variable). Sin git.

**Qué se hizo**
- Análisis de `structure.py`: intuiciones que se conservan, 6 errores que impiden ejecutarlo y
  7 problemas de diseño → [`docs/wiki/analisis-structure-py.md`](docs/wiki/analisis-structure-py.md).
- Brainstorming completo: 17 huecos de la idea original, 27 mejoras, ideas futuras y riesgos →
  [`ideas-y-mejoras.md`](docs/wiki/ideas-y-mejoras.md).
- Diseño (borradores v0.1):
  - [Visión](docs/wiki/vision.md): principios, no-objetivos, posicionamiento frente a OpenSpiel,
    Ludii, GDL, Gambit, boardgame.io, BGA, PettingZoo.
  - [Modelo formal](docs/wiki/modelo-formal.md): forma extensiva + FOSG + statecharts; 8 tipos de
    nodo; acciones con dominios; azar explícito; visibilidad por ubicación con handles opacos;
    simultaneidad, ventanas de reacción y carreras; tiempo; historial; propiedades derivadas.
  - [Lenguaje `.game`](docs/wiki/lenguaje-game.md): sintaxis con ejemplos (tres en raya, dilema del
    prisionero, Kuhn, fragmento de Mentiroso), módulos, mods con `extends`, combinadores.
  - [GameIR](docs/wiki/ir.md): IR de autor vs. resuelta, S-expresiones en JSON, hash de reglas y
    hash de interfaz, layout en sidecar.
  - [Arquitectura](docs/wiki/arquitectura.md), [protocolo](docs/wiki/protocolo.md),
    [Studio](docs/wiki/studio-editor-visual.md), [hub](docs/wiki/hub.md),
    [teoría de juegos](docs/wiki/teoria-de-juegos.md),
    [heurísticas e IA](docs/wiki/heuristicas-e-ia.md), [catálogo](docs/wiki/catalogo-de-juegos.md).
- [Roadmap](docs/wiki/roadmap.md) en 13 fases (F0–F12) con pesos, entregables, criterios de
  aceptación y dependencias. MVP jugable al 41 %, MVP de diseño al 51 %, IA al final.
- [Registro de decisiones](docs/wiki/decisiones.md) (16 ADR) y
  [preguntas abiertas](docs/wiki/preguntas-abiertas.md) (15, dos bloqueantes).
- `README.md` raíz, índice de la wiki con estado, `CLAUDE.md` con las normas de mantenimiento.

**Decisiones**
- Aceptadas (por el usuario): Python 3 + C++; extensión `.game`.
- Propuestas (pendientes de visto bueno): ADR 001–012 y 015 (IR canónica, expresiones puras,
  azar explícito, estados inmutables, visibilidad declarativa, statecharts, Python primero,
  git como backend, WebSocket+JSON, interoperabilidad, monorepo, TS+React).

**Pendiente / siguientes pasos**
- Respuestas a las preguntas 🔴 (mensaje cortado en "También quiero tener una…", licencia).
- Cerrar F0: `git init`, monorepo y herramientas, JSON Schema de la IR, 3 IR de validación.

**Progreso:** ≈ 0,5 % (F0: 1/8).
