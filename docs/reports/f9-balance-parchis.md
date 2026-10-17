# Balance de parchis

Reglas `sha256:8740b7f655561e3d3da661be58fc31e514f0325b7defbd08e4ad5c75253fbdaa` · 4 jugadores · bot de referencia `greedy` · 200 partidas.

## Ventaja por asiento

| Asiento | Pago medio [IC 95 %] | Primer puesto [IC 95 %] |
|---:|---|---|
| 0 | 0.020 [-0.222, 0.262] | 0.255 [0.200, 0.320] |
| 1 | -0.060 [-0.296, 0.176] | 0.235 [0.182, 0.298] |
| 2 | -0.060 [-0.296, 0.176] | 0.235 [0.182, 0.298] |
| 3 | 0.100 [-0.148, 0.348] | 0.275 [0.218, 0.341] |

Ningún asiento se aleja con significación del reparto justo (0.250).

## Tablas y duración

- Tablas (empate en cabeza): 0.0%
- Pasos por partida: media 755.2, mediana 752, p10–p90 585–936
- Decisiones por partida: 362.9

## Perfil de ramificación

- Acciones legales por decisión: 2.1 de media; decisiones forzadas (una sola acción): 30.7%
- Por décimas de la partida: 2.0 · 2.2 · 2.4 · 2.4 · 2.3 · 2.2 · 2.1 · 2.0 · 1.8 · 1.6

## Habilidad frente a suerte

- `greedy` contra `random`: primer puesto en 0.825 [0.766, 0.871] (la suerte daría 0.250).
- Peso de la habilidad: 0.77 (0 = pura suerte, 1 = el mejor gana siempre).

## Cadena de habilidad

| Peldaño | Contra | Primer puesto [IC 95 %] | ¿Mejora? |
|---|---|---|---|
| `greedy` | `random` | 0.825 [0.680, 0.913] | sí |
| `mcts:iterations=50,max_rollout=100,seconds=0.0` | `greedy` | 0.025 [0.004, 0.129] | no |
| `mcts:iterations=200,max_rollout=100,seconds=0.0` | `mcts:iterations=50,max_rollout=100,seconds=0.0` | 0.350 [0.221, 0.505] | no |

Profundidad de la cadena: **1** peldaños con mejora significativa.

## Tensión

- Cambios de líder por partida (según `Race`): 18.47
- El ganador va primero sin interrupción desde el 76% de la partida (de media).

## Acciones

| Acción | Usos | Victorias al usarla | Diferencia |
|---|---:|---:|---:|
| `advance` | 67766 | 25.0% | +0.0% |
| `count_bonus` | 4808 | 25.3% | +0.3% |

## Cobertura de reglas

Todas las acciones y transiciones aparecen en alguna partida.

## Kingmaking

- 31 de 791 decisiones examinadas al final de 10 partidas (3.9%): quien ya no podía ganar decidió quién ganaba.
