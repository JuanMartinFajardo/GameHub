# Modelo formal de un juego GameHub

> Estado: **v0.1** (Fase 0). Este documento es la *semántica* de GameHub: todo motor
> (Python, C++, WASM) y toda herramienta de análisis deben comportarse exactamente así. Su forma
> concreta como datos está en [`spec/ir/v0`](../../spec/ir/v0) ([GameIR](ir.md)).

## 1. Base teórica

El modelo combina tres tradiciones:

- **Juegos en forma extensiva** (árboles, conjuntos de información, nodos de azar, pagos).
- **FOSG** — *Factored-Observation Stochastic Games* (Kovařík, Schmid, Burch, Bowling, Lisý, 2022):
  en cada paso cada jugador recibe una observación factorizada en **pública** + **privada**. Es la
  base de los algoritmos modernos para información imperfecta (CFR, ReBeL, Student of Games).
- **Statecharts** (Harel, 1987): máquinas de estados **jerárquicas**, que es lo que de verdad es el
  "diagrama de flujo" de un juego (partida → ronda → baza → turno).

## 2. Definición

Un juego GameHub es una tupla

$$\mathcal{G} = \langle \Theta,\ N_\theta,\ R,\ \mathcal{C},\ \Sigma,\ \mathcal{F},\ \mathcal{A},\ \mathrm{Vis},\ u,\ \mathcal{T} \rangle$$

| Símbolo | Nombre | Descripción |
|---|---|---|
| $\Theta$ | Parámetros | Espacio de parámetros; $\theta\in\Theta$ se fija al crear la partida (nº de jugadores, variantes, tamaños). |
| $N_\theta=\{0..n-1\}$ | Asientos | Posiciones en las reglas. Pseudo-jugadores: **azar** $c$ y **sistema** $\bot$. Un *participante* (humano/bot) ocupa un asiento; no es lo mismo. |
| $R$ | Roles / equipos | $\rho: N\to 2^R$. Equipos = partición de $N$. |
| $\mathcal{C}$ | Componentes | Tipos (carta, ficha, dado…) con atributos de dominio finito; las instancias tienen identidad. |
| $\Sigma$ | Esquema de estado | Variables tipadas (globales, por jugador), **zonas** (colecciones de componentes) y **tableros** (rejillas, grafos). $S_\theta$ = valoraciones de $\Sigma$. |
| $\mathcal{F}$ | Flow | Statechart $(V,\kappa,\mathrm{parent},E)$: nodos, tipo de nodo, jerarquía, transiciones $(v,g,\varepsilon,v')$ con guarda $g$ y efecto $\varepsilon$. |
| $\mathcal{A}$ | Esquemas de acción | $(\text{nombre}, \text{parámetros con dominio } D(s), \text{guarda } g(s,i,x), \text{efecto } \varepsilon(s,i,x))$. |
| $\mathrm{Vis}$ | Visibilidad | Para cada ubicación $\ell$ del estado: $\mathrm{Vis}(\ell,s)\subseteq N$ (quién la ve, *dependiente del estado*). |
| $u$ | Pagos | $u: Z\to\mathbb{R}^n$ en nodos terminales; recompensas intermedias $r_i$ opcionales (RL). |
| $\mathcal{T}$ | Tiempo | Relojes y plazos (opcional). |

## 3. Elementos

### 3.1 Nodos del flow

| Tipo | Quién actúa | Semántica |
|---|---|---|
| `decision` | Un asiento (`actor`) | El actor elige una acción legal; se aplica de inmediato. |
| `simultaneous` | Conjunto (`actors`) | Cada actor envía una acción **oculta**; al completarse el conjunto se resuelven todas a la vez. |
| `window` | Conjunto elegible | Ventana de reacción ("¡Mentiroso!", cantar UNO, reclamar ficha en Mahjong). Modos: `priority`, `collect`, `race`. |
| `chance` | Azar $c$ | Única fuente de aleatoriedad: barajar, tirar dados, robar al azar. Distribución explícita. |
| `auto` | Sistema | Cálculo determinista (puntuar, comprobar victoria) y transición. |
| `phase` | — | Nodo compuesto con su propio `start`, `on_enter`, `on_exit`; puede ser un bucle (`for r in 1..R`, `repeat until …`). |
| `call` | — | Invoca un sub-flow reutilizable (p. ej. `std.tricktaking.Trick`). |
| `terminal` | — | Fin de la partida; define pagos, ranking y ganadores. |

Las **transiciones** salientes se evalúan **en orden**; gana la primera cuya guarda sea cierta y se
aplica su efecto. Si ninguna es cierta, es un *error de regla* (el verificador estático avisa de
transiciones no exhaustivas).

### 3.2 Acciones

- Una acción es un **esquema** `nombre(p₁: D₁, …, p_k: D_k)` con dominios que pueden depender del
  estado (`c: Card in hand[actor]`, `n: Int in 0..round`, `cs: subset(hand[actor], 1..4)`).
- **Legalidad** = parámetros dentro de dominio ∧ guarda cierta.
- **Acciones compuestas / construcción progresiva:** fijados $p_1..p_j$, el motor puede enumerar los
  valores legales de $p_{j+1}$. Sirve para las UI (eliges pieza → se iluminan destinos) y para RL
  (cabezas de acción autoregresivas).
- Los dominios deben ser **finitos y enumerables**. Parámetros "continuos" (una apuesta) se
  declaran con discretización o como intervalo entero.
- Cada parámetro tiene su visibilidad: en *Mentiroso* las cartas jugadas son privadas pero el
  número de cartas y lo que se *declara* son públicos.

### 3.3 Azar

- Solo los nodos `chance` (y el `setup`) contienen efectos aleatorios: `shuffle`, `roll`, `draw_random`,
  `sample(dist)`.
- Cada efecto aleatorio define un **espacio de resultados** $\Omega(\xi)$ con probabilidades.
  Si $|\Omega|$ es pequeño (un dado: 6) es **enumerable** (los algoritmos exactos lo recorren); si no
  (barajar 52 cartas: $52!$) es **solo muestreable** (algoritmos Monte Carlo).
- El motor implementa el muestreo con un RNG con semilla (PCG64, flujos separados por propósito)
  → **determinismo y replays**.
- Información incompleta "à la Harsanyi" (tipos privados) se modela como azar que asigna
  tipos con visibilidad privada.

### 3.4 Información

- **Ubicaciones** $\ell$: rutas de variables (`score[2]`), contenido de zonas, tamaño de zonas,
  atributos de componentes (`face`), campos de eventos.
- **Redacción:** $\mathrm{view}_i(s)$ = $s$ con cada $\ell$ tal que $i\notin\mathrm{Vis}(\ell,s)$
  sustituida por $\bot$ (conservando la "forma" pública declarada, p. ej. el tamaño de una mano).
- **Eventos:** cada efecto emite eventos (movimiento, revelación, asignación, resultado de azar) con
  su propia visibilidad. La observación de $i$ tras un paso es
  $o_i = (\mathrm{view}_i(s'), \text{eventos visibles para } i)$, factorizada en parte pública y privada.
- **Estado de información** de $i$: $I_i = (o_i^0, a_i^0, o_i^1, a_i^1, \dots)$. *Recuerdo perfecto*
  por construcción. Conjunto de información = historias con el mismo $I_i$.
- **Componentes ocultos sin identidad (anti-fugas, [ADR-019](decisiones.md)):** hay dos tipos de
  zona. Una **zona ordenada** (mazo, pila, fila de Memory) tiene posiciones públicas: quien no ve
  su contenido ve huecos por posición, y puede rastrear "la carta de arriba" igual que en la mesa.
  Una **bolsa** (una mano) es un multiconjunto: su orden no forma parte del estado y quien no ve su
  contenido solo ve su tamaño. Las componentes ocultas nunca exponen un identificador, así que no
  se filtra información por IDs ni por orden; lo que un jugador recuerde de lo que se reveló es
  información legítima (recuerdo perfecto).
- **`reveal` es un evento:** muestra valores a ciertos asientos sin cambiar la visibilidad
  persistente. Las cartas que quedan boca arriba usan `flip` y el predicado `item_face_up`.
- **Parámetros de acción:** su visibilidad se aplica a los demás asientos; el actor siempre ve su
  propia acción.
- **Fugas por legalidad:** si la guarda de una acción de $i$ depende de ubicaciones que $i$ no ve, el
  conjunto de acciones legales le filtra información. El análisis de flujo de información lo
  detecta y avisa (se puede marcar como intencionado).
- La visibilidad se declara **sobre los datos**, no por nodo: evita inconsistencias. La dependencia
  del nodo actual se expresa en la propia política: `@visible(all if at(Showdown) else owner)`.

### 3.5 Simultaneidad, ventanas y carreras

- `simultaneous`: envíos ocultos en un búfer $\beta$; al completarse se ejecuta `resolve` con la acción
  conjunta (orden canónico por asiento, o el declarado).
- `window` en modo `priority`: se pregunta en orden; el primer "no-pasar" resuelve.
  `collect`: todos responden en secreto; se resuelve por prioridad. `race`: tiempo real, gana la
  primera acción válida según la marca de tiempo **del servidor** (juegos de velocidad).
- Para análisis, `race` ≡ `collect` con desempate por prioridad (aproximación documentada).

### 3.6 Tiempo

Relojes por asiento (inicial, incremento), plazos por nodo, y `on_timeout` (acción por defecto,
pasar, acción aleatoria legal, derrota). El tiempo es parte de la *partida* (servidor), no del
análisis, salvo que el juego lo modele como estado discreto.

### 3.7 Historial

Las reglas solo pueden leer el estado actual **más** rasgos de historial mantenidos por el motor y
declarados (`history.count(position)`, `history.last(k)`). La configuración sigue siendo
markoviana. Ejemplos: triple repetición en ajedrez, "no repetir la jugada anterior".

### 3.8 Resultados

Nodo terminal → vector de pagos $u(z)\in\mathbb{R}^n$, ranking (orden parcial) y ganadores. Juegos
cooperativos de mesa (Hanabi) = pago común. Recompensas intermedias `reward` solo para RL.

## 4. Semántica operacional

Una **configuración** es $\xi = (s, \bar v, \beta, h, t)$: valoración del estado, pila de nodos
activos del statechart, búfer de envíos pendientes, rasgos de historial y relojes. El motor:

1. **Avanza hasta quiescencia:** ejecuta nodos `auto`, entradas/salidas de `phase` y `call` hasta
   llegar a un *punto de decisión*, un *punto de azar* o un *terminal*. (Ciclos de nodos
   automáticos sin progreso se detectan estáticamente y, en ejecución, con un límite de pasos.)
2. En un punto de decisión expone $\mathrm{Act}(\xi)\subseteq N$ y $L_i(\xi)$ para cada $i$ activo.
3. En un punto de azar expone $P(\cdot\mid\xi)$ sobre $\Omega(\xi)$ (enumerable) o un muestreador.
4. Aplicar una acción: validar dominio + guarda → efecto → transiciones → `on_exit`/`on_enter` →
   eventos → volver a 1.

**Determinismo:** $(\mathcal{G}, \theta, \text{semilla}, \text{secuencia de acciones}) \Rightarrow$
trayectoria única. Un *replay* es exactamente esa tupla.

## 5. Propiedades que se derivan automáticamente

| Propiedad | Definición | Cómo se determina |
|---|---|---|
| Determinista | No hay nodos `chance` alcanzables | Estático |
| Información perfecta | Todo visible para todos y sin envíos ocultos | Estático |
| Suma cero / constante | $\sum_i u_i(z)=k\ \forall z$ | Simbólico si los pagos son tabla/expresión simple; si no, empírico |
| Pago común (cooperativo) | $u_i=u_j\ \forall i,j$ | Estático / simbólico |
| Simultáneo | Hay nodos `simultaneous` o `window collect` | Estático |
| Imparcial (CGT) | 2 jugadores alternos, mismas opciones, "normal play" | Estático (+ declaración) |
| Horizonte finito | Flow acíclico tras desplegar bucles acotados, o `max_steps` | Estático / declarado |
| Tamaño | $|S|$, profundidad, ramificación, nº de conjuntos de información | Estimador de Knuth + playouts |

## 6. Correspondencia con formalismos clásicos

| Formalismo | Cómo se obtiene desde un juego GameHub |
|---|---|
| Forma extensiva (EFG) | Desplegar configuraciones; los simultáneos se secuencializan con conjuntos de información |
| Forma normal (matriz) | Directa si es un único nodo simultáneo; si no, estrategias puras reducidas (exponencial) |
| FOSG | Directa: observaciones públicas/privadas por paso |
| MDP / POMDP | 1 jugador (Solitario = POMDP con azar) |
| Juego estocástico | Flow con ciclos (sin horizonte fijo) |
| Teoría combinatoria (CGT) | 2 jugadores, alternado, info perfecta, sin azar; sumas vía combinador `sum` |
| Juego cooperativo (función característica) | Objeto *derivado* $v(C)$ (p. ej. valor maxmin de cada coalición), no un flow |

## 7. Restricciones que garantizan todo lo anterior

- **Expresiones totales:** sin recursión general; bucles solo sobre colecciones finitas.
- **Sin efectos en expresiones:** solo los bloques de efectos modifican el estado.
- **Sin fuentes ocultas de no determinismo:** ni reloj ni RNG accesibles desde expresiones.
- **Dominios de acción finitos.**
- **Errores de regla** (índice fuera de rango, transición no encontrada) abortan la partida con
  diagnóstico localizado; tests y fuzzing buscan eliminarlos antes de publicar.

Ver: [Lenguaje `.game`](lenguaje-game.md) · [GameIR](ir.md) · [Teoría de juegos](teoria-de-juegos.md)
