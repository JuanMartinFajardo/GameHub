# Balance de wizard

Reglas `sha256:01ca464cb4e2ed84219b46b6e0862972323008c78abe2d583ef3d914fa08a6d4` · 3 jugadores · bot de referencia `greedy` · 200 partidas.

## Ventaja por asiento

| Asiento | Pago medio [IC 95 %] | Primer puesto [IC 95 %] |
|---:|---|---|
| 0 | -115.150 [-133.347, -96.953] | 0.320 [0.259, 0.388] |
| 1 | -121.700 [-141.333, -102.067] | 0.330 [0.269, 0.398] |
| 2 | -106.550 [-123.004, -90.096] | 0.350 [0.287, 0.418] |

Ningún asiento se aleja con significación del reparto justo (0.333).

## Tablas y duración

- Tablas (empate en cabeza): 2.0%
- Pasos por partida: media 711.3, mediana 711, p10–p90 710–713
- Decisiones por partida: 691.3

## Perfil de ramificación

- Acciones legales por decisión: 5.8 de media; decisiones forzadas (una sola acción): 14.1%
- Por décimas de la partida: 2.9 · 4.0 · 4.9 · 5.2 · 6.0 · 6.5 · 7.1 · 7.0 · 7.1 · 7.3

## Habilidad frente a suerte

- `greedy` contra `random`: primer puesto en 0.945 [0.904, 0.969] (la suerte daría 0.333).
- Peso de la habilidad: 0.92 (0 = pura suerte, 1 = el mejor gana siempre).

## Cadena de habilidad

| Peldaño | Contra | Primer puesto [IC 95 %] | ¿Mejora? |
|---|---|---|---|
| `greedy` | `random` | 0.983 [0.859, 0.998] | sí |
| `ismcts:max_rollout=60,seconds=0.005` | `greedy` | 0.533 [0.361, 0.698] | sí |

Profundidad de la cadena: **2** peldaños con mejora significativa.

## Tensión

- Cambios de líder por partida (según `Tricks`): 22.38
- El ganador va primero sin interrupción desde el 59% de la partida (de media).

## Acciones

| Acción | Usos | Victorias al usarla | Diferencia |
|---|---:|---:|---:|
| `bid` | 12000 | 33.3% | +0.0% |
| `choose` | 252 | 32.7% | -0.6% |
| `play` | 126000 | 33.3% | +0.0% |

## Cobertura de reglas

Todas las acciones y transiciones aparecen en alguna partida.

## Kingmaking

- 10 de 872 decisiones examinadas al final de 4 partidas (1.1%): quien ya no podía ganar decidió quién ganaba.
