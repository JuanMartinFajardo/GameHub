# Heurísticas, bots, arena e IA

> Estado: **diseño v0.1**. Heurísticas y bots clásicos en la Fase 9; IA (RL, Deep RL, LLM) en la
> Fase 11, como pediste: lo último.

## 1. Heurísticas como artefactos de primera clase

Una heurística es conocimiento sobre el juego que **no** es una regla: funciones de evaluación,
orden de jugadas, políticas de simulación, reglas de decisión. Viven en el repo del juego
(`heuristics/`) y se versionan, comparan y publican como todo lo demás.

Se escriben **en el mismo lenguaje de expresiones** (así corren en el motor C++ a toda velocidad)
o como plugin (Python, C++, red neuronal ONNX):

```game
heuristic Material for Chess {
  feature material(s) = sum(p in pieces(s, me)  : value(p.kind))
                      - sum(p in pieces(s, opp) : value(p.kind))
  feature mobility(s) = len(legal_moves(s, me)) - len(legal_moves(s, opp))
  feature center(s)   = count(p in pieces(s, me) : p.square in {d4, d5, e4, e5})

  eval = 1.0 * material + 0.1 * mobility + 0.3 * center      // pesos ajustables
  order moves by captured_value desc, then checks first        // ordenación para alfa-beta
}
```

**Usos:** evaluación en el corte de minimax/expectimax · *prior* y política de *rollout* en MCTS ·
evaluación de hojas en ISMCTS/PIMC · políticas directas para bots basados en reglas.

**Ajuste de pesos:** CMA-ES, SPSA, *Texel tuning* (regresión logística sobre resultados), algoritmos
genéticos; la arena mide si un ajuste mejora de verdad (con SPRT).

## 2. Tipos de bots

| Tipo | Ejemplos | Cuándo |
|---|---|---|
| Aleatorio | Uniforme sobre acciones legales | Fuzzing, línea base |
| Basado en reglas | Lista de prioridades ("si puedes ganar la baza con la carta más baja, hazlo") | Juegos de cartas, tutoriales |
| Búsqueda | Minimax/alfa-beta, expectimax, MCTS, **ISMCTS**, **PIMC** (determinización, usado en Skat) | Info perfecta / imperfecta |
| Teoría de juegos | Estrategia de equilibrio (CFR) | Juegos pequeños de info imperfecta |
| Aprendido | PPO, DQN, AlphaZero, NFSP, Deep CFR | Fase 11 |
| LLM | Lee las reglas autogeneradas y la observación en texto | Fase 11 |

Interfaz común (Python; equivalentes en C++ y TS), implementada en la Fase 3 y **la misma en
proceso y por la red** ([ADR-043](decisiones.md)):

```python
class Agent:
    def act(self, observation, legal) -> Action: ...    # obligatorio
    def reset(self, observation): ...                   # opcional: al empezar cada partida
    def observe(self, observation): ...                 # opcional: cuando no le toca
    def end(self, result): ...                          # opcional: al terminar
```

`observation` tiene `seat`, `view` y `events` (y, por la red, `clock` y `game`); `legal` son las
acciones legales como `Action`. `gamehub bot run agente.py --room K7F-Q2P` juega con un archivo
que define `make_agent(game, seat)`, una clase `Agent` o una función `act`.

## 3. Arena

- Torneos *round-robin*, suizos, *gauntlet*; partidas espejo (mismos repartos con asientos
  rotados) para reducir varianza en juegos de azar.
- Ratings **Elo / Glicko-2** (2 jugadores) y **TrueSkill** (n jugadores, equipos), siempre **por
  hash de reglas**.
- Bots de terceros en sandbox (proceso/contenedor/WASM) con límites de CPU, memoria y tiempo.
- Bots locales o conectados por el protocolo (un bot es un cliente más).

## 4. Analítica de diseño ("¿está equilibrado mi juego?")

| Métrica | Pregunta que responde |
|---|---|
| Ventaja por asiento | ¿Gana demasiado el primer jugador? |
| Tasa de empates, duración | ¿Las partidas son demasiado largas o tablas? |
| Perfil de ramificación | ¿Hay momentos sin decisiones reales? |
| **Profundidad de habilidad** (*skill chain*) | ¿Cuántos niveles de juego distintos caben? |
| **Habilidad vs. suerte** | ¿Cuánto mejor rinde un bot fuerte que uno aleatorio? |
| Cambios de líder, decisividad | ¿Hay tensión hasta el final? |
| **Estrategias dominantes** | ¿Hay una acción que siempre conviene? |
| **Cobertura de reglas** | ¿Hay reglas que nunca se usan en partidas reales? |
| *Kingmaking* (n jugadores) | ¿Un jugador que ya no puede ganar decide quién gana? |

Estas métricas alimentan el **Balance CI** de los PRs del [hub](hub.md).

## 5. IA (Fase 11)

- **Tensorización automática** desde la IR: zonas y tableros → planos one-hot, contadores →
  escalares normalizados, acciones → índices con máscara de legalidad. Cualquier juego del
  catálogo es entrenable sin escribir código de codificación.
- **Adaptadores:** Gymnasium (1 agente), PettingZoo (AEC/paralelo), OpenSpiel.
- **Entornos vectorizados en C++** (miles de partidas en paralelo).
- **Algoritmos:** PPO, DQN; **AlphaZero** (MCTS en C++ + red en PyTorch); MuZero; info imperfecta:
  NFSP, Deep CFR, PSRO, R-NaD, ReBeL.
- **Exportación ONNX** → inferencia en C++ y en el navegador (onnxruntime-web).
- **Agentes LLM:** observación y reglas en texto; herramientas = acciones legales.
- **Diseño asistido por IA:** reglas en lenguaje natural → borrador `.game`; explicación de reglas;
  sugerencias de balance basadas en la analítica.

## 6. Juego limpio humano vs. bot

- **Juegos de memoria:** política de *recuerdo* del bot (`recall: none | last(k) | perfect`); sin
  ella un bot nunca olvida y el juego pierde sentido.
- **Juegos de velocidad:** tiempo de reacción mínimo/jitter para bots en nodos `race`.
- Partidas puntuadas marcadas como "con bots" o "solo humanos".
