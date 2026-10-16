# Glosario

| Término | Inglés | Definición en GameHub |
|---|---|---|
| Abandono | forfeit | Rendirse, salir en partida o agotar el plazo con `on_timeout: forfeit`: el asiento queda el último y un bot juega por él hasta el final. |
| Acción | action | Elección de un asiento en un punto de decisión: nombre + parámetros con dominio. |
| Acción legal | legal action | Acción cuyos parámetros están en dominio y cuya guarda es cierta. |
| Actualización | update | Mensaje del servidor con lo que ha pasado (una acción y el azar que la sigue) y el estado resultante para el destinatario; numeradas con `seq` sin huecos. |
| Agente / bot | agent / bot | Programa que juega: `act(observación, acciones legales) → acción`. El mismo agente juega en proceso o por la red. |
| Anfitrión | host | Participante que administra una sala: configura, abre o reserva asientos, pone bots, echa a alguien. |
| Asiento | seat | Posición en las reglas (0..n-1). Lo ocupa un participante. |
| Aviso | warning | Diagnóstico que no impide compilar (`W…`): nodo inalcanzable, posible fuga de información, declaración sin usar… |
| Azar / naturaleza | chance / nature | Pseudo-jugador que resuelve los nodos `chance` según distribuciones explícitas. |
| Azar verificable | provably fair | Compromiso de la semilla del servidor antes de jugar, semillas de los jugadores y revelación al final (`gamehub-fair/1`): nadie puede elegir el azar y cualquiera lo comprueba. |
| Biblioteca estándar | standard library | Módulos `std.…` que vienen con GameHub (`std.cards`, `std.dice`, `std.grid`, `std.graph`). |
| Bolsa | bag | Zona sin orden (multiconjunto), típica de las manos; quien no ve su contenido solo ve su tamaño. |
| Catálogo de operadores | operator catalog | `spec/ir/v0/ops.json`: lista cerrada de expresiones, sentencias y selectores de la IR. |
| Cobertura de reglas | rule coverage | Cuántas veces se pasó por cada nodo, acción y transición en las partidas masivas del simulador; lo que nunca se usó se marca en el diagrama. |
| Código de sala | room code | 6 caracteres de Crockford base32 (`K7F-Q2P`) para entrar en una sala. |
| Código generado | codegen | Las expresiones y funciones de la IR escritas como código de Python y compiladas con `exec` (`gamehub.engine.codegen`): dan lo mismo que los cierres de referencia, unas dos veces más rápido. |
| Combinador | combinator | Juego construido a partir de otro transformando su IR: `repeat(G, rounds: n)`, `best_of(G, rounds: n)`. |
| Configuración | configuration | Estado completo del motor: valores + nodos activos + envíos pendientes + historial + relojes. |
| Conjunto de información | information set | Historias que un jugador no puede distinguir (mismo estado de información). |
| Construcción progresiva | progressive action building | Elegir los parámetros de una acción uno a uno, consultando los legales en cada paso. |
| Constructor de acciones | action builder | Parte de la UI genérica que compone una acción argumento a argumento con los valores que permiten las acciones legales (enumeradas o con `query_actions`). |
| Diagnóstico | diagnostic | Error o aviso del compilador con código, posición, explicación y ayuda (al estilo de rustc). |
| Disposición (del diagrama) | layout | Dónde va cada caja del diagrama del Studio: la calcula ELK y la ajusta el usuario; se guarda en `<juego>.layout.json`, fuera de las reglas. |
| Efecto | effect | Sentencia que modifica el estado (`assign`, `move`, `reveal`…). Solo en bloques de efectos. |
| En este dispositivo | hot-seat | Varias personas jugando por turnos en la misma pantalla; en la app web, con una conexión por asiento y la pantalla tapada entre turnos si hay información oculta. |
| Espectador | spectator | Participante sin asiento: ve la vista pública (u omnisciente, si la sala lo permite), con retardo opcional. |
| Estado de información | information state | Secuencia de observaciones y acciones propias de un jugador. |
| Evento | event | Registro de algo que ocurrió (movimiento, revelación…), con su visibilidad. |
| Flow | flow | El diagrama de flujo del juego: statechart jerárquico de nodos y transiciones. |
| Fuga de información | information leak | Dato oculto que llega a quien no debería verlo (por el estado, un evento, el camino o las jugadas legales); `gamehub check` avisa (W405). |
| GameIR | GameIR | Representación intermedia canónica (JSON) del juego; la fuente de verdad. |
| Guarda | guard | Condición booleana pura de una acción (`requires`) o transición (`when`). |
| Hash de interfaz | interface hash | Huella de los esquemas de vista/acciones/eventos; compatibilidad de UIs y bots. |
| Hash de reglas | rules hash | Huella de la IR resuelta; identifica exactamente una versión de las reglas. |
| Huella (digest) | digest | SHA-256 de la instantánea de un estado; permite comparar motores paso a paso. |
| Instantánea | snapshot | Configuración completa de un estado en JSON canónico (incluye caras de cartas y envíos pendientes). |
| Invariante | invariant | Condición que debe cumplirse en todo estado alcanzable; `gamehub test` la comprueba en tests y partidas aleatorias. |
| IR núcleo / resuelta | core IR | La IR sin azúcar que ejecutan los motores; la genera el compilador de Nomos. |
| Lockfile | lockfile | `game.lock`: commit exacto de cada dependencia git de un paquete. |
| Memo (de funciones) | memoization | Resultados de funciones de la IR guardados según de qué dependen: para siempre si solo de sus argumentos (*static*), mientras no cambie el estado si lo leen (*state*). |
| Mod / variante | mod / variant | Juego que extiende otro (`extends`) con `override`, `remove` y `extend node`. |
| Módulo | module | Archivo `.game` cuyas declaraciones (`enum`, `struct`, `fn`, juegos) se usan con `import`. |
| Nodo | node | Caja del flow: `decision`, `simultaneous`, `window`, `chance`, `auto`, `phase`, `terminal` (`call`, más adelante). |
| Nomos | Nomos | El lenguaje de descripción de juegos de GameHub (archivos `.game`). |
| Observación | observation | Lo que un jugador recibe tras un paso: vista redactada + eventos visibles (pública + privada). |
| Observador público | public observer | Quien no ocupa ningún asiento (`PUBLIC` en el motor): ve lo que la visibilidad permite a quien no es dueño de nada. |
| Operación (del Studio) | edit operation | Un cambio del diagrama o de un formulario (`addNode`, `addTransition`, `updateAction`…) que se aplica al árbol del `.game`; el texto se reescribe solo donde cambió. |
| Pagos | payoffs | Vector de utilidades en un nodo terminal. |
| Palo efectivo | effective suit | En `std.tricktaking`, el palo con el que cuenta una carta en una baza (un entero; −1 = se puede jugar siempre, como el mago o el bufón de Wizard). |
| Paquete | package | Directorio de un juego con su `game.toml` (nombre, versión, dependencias). |
| Participante | participant | Persona o bot en una sala: jugador (sentado) o espectador. |
| Partida | match | Ejecución concreta de un juego: parámetros + semilla + acciones. |
| Perft | perft | Número de secuencias de jugadas legales hasta una profundidad (`gamehub perft`); en ajedrez, la prueba estándar de un generador de jugadas (*perft(5)* = 4 865 609). |
| Pistas de presentación | UI hints | La sección `ui { … }` de un juego: cómo dibujar sus variables, nombres traducidos, símbolos, colores, cartas, cómo elegir argumentos. No son reglas: no cuentan para el hash. |
| Plazo / reloj | deadline / clock | Tiempo para decidir: fijo por turno (`move`) o un tiempo total por asiento con incremento (`match`); al vencer se aplica `on_timeout`. |
| Plugin nativo | native plugin | Implementación en WebAssembly de una función `@native("m.f")`, que debe dar exactamente lo mismo que su cuerpo en Nomos (la referencia). ABI `gamehub-native/1`. |
| Punto de decisión | decision point | Configuración en la que uno o más asientos deben actuar. |
| Replay | replay | Tupla (hash de reglas, parámetros, semilla, acciones) que reproduce una partida exacta. |
| Revancha | rematch | Otra partida en la misma sala y con los mismos asientos, cuando todos vuelven a declararse listos. |
| Sala | room | Instancia alojada de un juego con su código, asientos, configuración y partidas encadenadas. |
| Servidor de lenguaje | language server (LSP) | `gamehub lsp`: diagnósticos, autocompletado, hover, definición, renombrar… para cualquier editor; el Studio usa el mismo por WebSocket. |
| Sesión | session | La participación de alguien en una sala, identificada por un token secreto que permite reconectarse. |
| Statechart | statechart | Máquina de estados jerárquica (Harel); el modelo del flow. |
| Studio | Studio | El editor visual de GameHub (`gamehub studio`): diagrama y texto a la vez, inspector, simulador y herramientas. |
| Test | test | Bloque `test "…" { … }` de un juego: una partida guionizada con comprobaciones (`play`, `expect`, `chance where`, `set`). |
| Traza de conformidad | conformance trace | Replay con semilla fija que todo motor debe reproducir bit a bit (`spec/conformance`). |
| Turno vigente | current turn | Desde la actualización en que un asiento puede actuar hasta que actúa o se llega a otro nodo; un `act` decidido antes se rechaza (`stale_seq`). |
| Ubicación | location | Parte direccionable del estado (variable, zona, tamaño, atributo) sobre la que se define la visibilidad. |
| UI genérica | generic UI | La interfaz que dibuja y deja jugar cualquier juego a partir de su IR, sin escribir nada (`@gamehub/auto-ui`). |
| UI propia | custom UI | Interfaz hecha a mano para un juego (`games/<juego>/ui`, con `defineGameUi`); la app la usa en vez de la genérica. |
| Ventana de reacción | reaction window | Nodo `window`: varios asientos pueden responder a un evento ("¡Mentiroso!"). |
| Vista | view | Estado redactado para un asiento concreto. |
| Zona | zone | Colección ordenada de componentes con posiciones públicas (mazo, pila, fila). Ver también *bolsa*. |
