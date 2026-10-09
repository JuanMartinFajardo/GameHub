# Módulo de teoría de juegos

> Estado: **diseño v0.1**. v1 en Python con puentes a Gambit/OpenSpiel (Fase 7); a escala en
> C++ (Fases 8–9).

## 1. Filosofía: calcular solo lo viable, y saber de antemano si lo es

Antes de lanzar un cálculo, el **asesor de viabilidad** clasifica el juego y estima su tamaño:

1. **Clasificación** estática ([modelo formal §5](modelo-formal.md)): jugadores, azar, información
   perfecta, simultaneidad, suma cero, horizonte.
2. **Estimación de tamaño:** ramificación y profundidad por playouts; tamaño del árbol con el
   **estimador de Knuth** (1975); estados distintos por hashing; nº de conjuntos de información.
3. **Recomendación** (umbrales orientativos, a calibrar):

| Tamaño | Qué es viable |
|---|---|
| ≤ 10⁶ estados | Solución exacta en Python (árbol completo, matriz, Nash) |
| ≤ 10⁹ estados | Exacta en C++ (alfa-beta con tablas de transposición, análisis retrógrado) |
| ≤ 10⁷ conj. de información | CFR tabular en C++ |
| Mayor | Aproximado: MCTS/ISMCTS, MCCFR, heurísticas, RL; métricas empíricas |

```bash
gamehub analyze ajedrez --feasibility
# perfect-info · determinista · suma cero · ramificación≈31 · profundidad≈80
# árbol ≈ 10^120 → solución exacta inviable. Recomendado: alfa-beta + heurística, MCTS, arena.
```

## 2. Representaciones

Árbol (forma extensiva) · DAG con transposiciones · grafo de estados (juegos cíclicos) ·
**forma normal (matriz)** · forma secuencial · árbol público (FOSG) · forma de función
característica (cooperativos).

## 3. Catálogo de algoritmos por clase de juego

| Clase | Algoritmos | Resultado |
|---|---|---|
| Info perfecta, determinista, 2J suma cero | Minimax, negamax, **alfa-beta** (+ profundización iterativa, tablas de transposición Zobrist, ordenación), **análisis retrógrado**, proof-number search | Valor del juego, estrategia óptima, "resuelto" |
| Info perfecta con azar | Expectimax, *-minimax (Star1/Star2), iteración de valor | Valor esperado, política óptima |
| Info perfecta, n jugadores / suma general | **Inducción hacia atrás → equilibrio perfecto en subjuegos**; max^n, paranoid | Perfil SPE |
| Forma normal | Equilibrios puros, **eliminación iterada de estrategias dominadas**, *support enumeration*, **Lemke–Howson**, **PL para suma cero**, **equilibrio correlacionado** (PL), frente de **Pareto**, óptimo social, precio de la anarquía/estabilidad, ESS, dinámica del replicador, fictitious play, QRE (logit) | Equilibrios, dominancia, eficiencia |
| Info imperfecta (forma extensiva) | PL en forma secuencial (2J suma cero, exacto), **CFR / CFR+ / DCFR / MCCFR**, mejor respuesta, **explotabilidad / NashConv**, ISMCTS, PIMC | Equilibrio aproximado con cota de error |
| Un jugador (MDP/POMDP) | Programación dinámica, A*/IDA*, beam search, búsqueda con determinización | Política óptima, % de partidas ganables (Solitario) |
| Juegos repetidos | **Torneos tipo Axelrod**, estrategias como autómatas, dinámica evolutiva (Moran) | Rankings, estabilidad evolutiva |
| Combinatorios (CGT) | **Sprague–Grundy** (valores de Grundy, mex, suma-nim), clases de resultado (N, P, L, R), formas canónicas, temperatura; sumas de juegos | Valor del juego, jugadas ganadoras |
| Cooperativos (función característica) | v(C) derivada (valor maxmin de la coalición), **valor de Shapley**, **núcleo** (PL), **nucléolo**, índice de Banzhaf, solución de negociación de Nash | Repartos estables/justos |

## 4. Visualizaciones (Studio y notebooks)

- **Explorador de árbol** plegable, con conjuntos de información enlazados y valores en cada nodo.
- **Vista de matriz** con mejores respuestas subrayadas y equilibrios resaltados.
- Gráfico de **convergencia** (explotabilidad vs. iteraciones de CFR).
- Gráfico de **Pareto** y de bienestar social.
- Tablas de Grundy; perfiles de estrategia como tablas por conjunto de información.

## 5. Interoperabilidad

- **Gambit:** exportar `.efg` / `.nfg` y usar `pygambit` (sus solvers de n jugadores son maduros).
- **OpenSpiel:** envolver cualquier juego GameHub como juego `pyspiel` → acceso a todo su catálogo
  de algoritmos desde el primer día.
- **CGSuite:** exportar posiciones de juegos combinatorios para formas canónicas complejas.

## 6. Resultados de referencia (tests de validación)

| Juego | Resultado conocido |
|---|---|
| Tres en raya | Valor = empate; 5 478 posiciones legales; 255 168 partidas posibles |
| Dilema del prisionero | Único NE (D, D), dominado en Pareto por (C, C) |
| Piedra-papel-tijera | NE mixto único (1/3, 1/3, 1/3), valor 0 |
| Matching pennies | NE mixto (1/2, 1/2), valor 0 |
| Póker de Kuhn | Valor para el primer jugador = −1/18 |
| Nim | Posición P ⇔ suma-nim (XOR) = 0 |
| Conecta 4 (7×6) | Gana el primer jugador (Allis / Allen, 1988) |
| Ajedrez (perft desde la posición inicial) | 20 · 400 · 8 902 · 197 281 · 4 865 609 |

## 7. Ejemplos de uso

```bash
gamehub analyze prisoners-dilemma --nash --pareto
gamehub analyze tictactoe --solve
gamehub analyze kuhn-poker --cfr 100000 --exploitability
gamehub analyze nim --grundy --params heaps=3,5,7
gamehub analyze wizard --feasibility
gamehub export kuhn-poker --to gambit-efg
```

```python
from gamehub import load
from gamehub.analysis import normal_form, nash

g = load("prisoners-dilemma")
M = normal_form(g)              # matriz de pagos 2×2×2
print(nash.support_enumeration(M))   # [((0,1), (0,1))]  → (Defect, Defect)
```
