# Glosario

| Término | Inglés | Definición en GameHub |
|---|---|---|
| Acción | action | Elección de un asiento en un punto de decisión: nombre + parámetros con dominio. |
| Acción legal | legal action | Acción cuyos parámetros están en dominio y cuya guarda es cierta. |
| Asiento | seat | Posición en las reglas (0..n-1). Lo ocupa un participante. |
| Aviso | warning | Diagnóstico que no impide compilar (`W…`): nodo inalcanzable, posible fuga de información, declaración sin usar… |
| Azar / naturaleza | chance / nature | Pseudo-jugador que resuelve los nodos `chance` según distribuciones explícitas. |
| Biblioteca estándar | standard library | Módulos `std.…` que vienen con GameHub (`std.cards`, `std.dice`, `std.grid`, `std.graph`). |
| Bolsa | bag | Zona sin orden (multiconjunto), típica de las manos; quien no ve su contenido solo ve su tamaño. |
| Catálogo de operadores | operator catalog | `spec/ir/v0/ops.json`: lista cerrada de expresiones, sentencias y selectores de la IR. |
| Combinador | combinator | Juego construido a partir de otro transformando su IR: `repeat(G, rounds: n)`, `best_of(G, rounds: n)`. |
| Configuración | configuration | Estado completo del motor: valores + nodos activos + envíos pendientes + historial + relojes. |
| Conjunto de información | information set | Historias que un jugador no puede distinguir (mismo estado de información). |
| Construcción progresiva | progressive action building | Elegir los parámetros de una acción uno a uno, consultando los legales en cada paso. |
| Diagnóstico | diagnostic | Error o aviso del compilador con código, posición, explicación y ayuda (al estilo de rustc). |
| Efecto | effect | Sentencia que modifica el estado (`assign`, `move`, `reveal`…). Solo en bloques de efectos. |
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
| Mod / variante | mod / variant | Juego que extiende otro (`extends`) con `override`, `remove` y `extend node`. |
| Módulo | module | Archivo `.game` cuyas declaraciones (`enum`, `struct`, `fn`, juegos) se usan con `import`. |
| Nodo | node | Caja del flow: `decision`, `simultaneous`, `window`, `chance`, `auto`, `phase`, `terminal` (`call`, más adelante). |
| Nomos | Nomos | El lenguaje de descripción de juegos de GameHub (archivos `.game`). |
| Observación | observation | Lo que un jugador recibe tras un paso: vista redactada + eventos visibles (pública + privada). |
| Pagos | payoffs | Vector de utilidades en un nodo terminal. |
| Paquete | package | Directorio de un juego con su `game.toml` (nombre, versión, dependencias). |
| Participante | participant | Humano, bot o espectador conectado a una sala. |
| Partida | match | Ejecución concreta de un juego: parámetros + semilla + acciones. |
| Punto de decisión | decision point | Configuración en la que uno o más asientos deben actuar. |
| Replay | replay | Tupla (hash de reglas, parámetros, semilla, acciones) que reproduce una partida exacta. |
| Sala | room | Instancia alojada de un juego con código de acceso. |
| Statechart | statechart | Máquina de estados jerárquica (Harel); el modelo del flow. |
| Test | test | Bloque `test "…" { … }` de un juego: una partida guionizada con comprobaciones (`play`, `expect`, `chance where`, `set`). |
| Traza de conformidad | conformance trace | Replay con semilla fija que todo motor debe reproducir bit a bit (`spec/conformance`). |
| Ubicación | location | Parte direccionable del estado (variable, zona, tamaño, atributo) sobre la que se define la visibilidad. |
| Ventana de reacción | reaction window | Nodo `window`: varios asientos pueden responder a un evento ("¡Mentiroso!"). |
| Vista | view | Estado redactado para un asiento concreto. |
| Zona | zone | Colección ordenada de componentes con posiciones públicas (mazo, pila, fila). Ver también *bolsa*. |
