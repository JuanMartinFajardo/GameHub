# El Hub — "GitHub para juegos"

> Estado: **diseño v0.1** (Fase 0). v0 local (Fase 2), web completa (Fase 10).

## 1. Idea

Cada juego es un **repositorio git** con un `game.toml`. El hub **no reinventa git**: lo usa por
debajo (Forgejo/Gitea embebido o cualquier host git) y añade encima todo lo que entiende de juegos:
reglas renderizadas, diagramas, partidas, análisis, bots, interfaces y diffs semánticos.

## 2. Flujo local-first (CLI)

```bash
gamehub new mi-juego --template tricktaking   # crea paquete con game.toml + .game + tests
gamehub check && gamehub test                 # verificar
gamehub publish                               # sube versión (semver) al registro
gamehub clone juanma/wizard                   # = git clone + resolución de dependencias
gamehub fork juanma/wizard --as wizard-sin-bufones
gamehub diff v1.2.0..main                     # diff semántico de reglas
gamehub host wizard --players 4               # jugar
```

Ramas, commits y merges son git normal. `gamehub` añade los pasos que git no sabe hacer.

## 3. Entidades

| Entidad | Descripción |
|---|---|
| Repositorio | Juego o **biblioteca** (módulos reutilizables: barajas, bazas, apuestas) |
| Versión (release) | semver + **hash de reglas** + hash de interfaz; inmutable |
| Rama / fork | Variantes y mods (git) |
| Propuesta (PR) | Cambio de reglas con diff textual, **semántico**, **visual** y de **balance** |
| Partida / replay | Ligada al hash de reglas exacto |
| Bot | Agente publicado, con ratings por versión de reglas |
| Análisis | Resultado cacheado (Nash, árbol, métricas) indexado por hash de reglas |
| Interfaz (Pages) | UI estática alojada por el hub, compatible con un hash de interfaz |

## 4. Página de un juego

`Reglas` (reglamento autogenerado + diagrama interactivo) · `Código` · **`Jugar`** (crear sala con
un clic) · `Análisis` (clasificación, tamaño, equilibrios si son viables) · `Bots` (ranking de la
arena) · `Interfaces` (UIs compatibles) · `Variantes` (**árbol genealógico** del juego: forks y
ancestros, p. ej. Whist → Oh Hell → Wizard) · `Partidas` · `Issues` · `Propuestas`.

## 5. Diff semántico y "Balance CI"

Un PR de reglas se revisa en cuatro capas:

1. **Diff de texto** (git normal).
2. **Diff semántico de IR:** "acción `bid`: dominio `0..round` → `0..round+1`",
   "nodo `DealerChoosesTrump` eliminado", "pago de `Exact`: `20+10·w` → `30+10·w`".
3. **Diff visual:** el diagrama con nodos y flechas añadidos/eliminados/modificados coloreados.
4. **Diff de comportamiento (Balance CI):** la misma batería de bots juega N partidas con cada
   versión y se comparan métricas: ventaja por asiento, duración, tasa de empates, cobertura de
   reglas, diferencia entre bots fuertes y aleatorios (habilidad vs. suerte)… Igual que un CI de
   rendimiento, pero para el diseño del juego.

## 6. Versionado automático

Comparando el **hash de interfaz** entre versiones, el hub detecta cambios incompatibles para UIs y
bots (p. ej. una acción nueva con parámetros distintos) y **exige subir la versión major**. Cambios
de reglas que no tocan la interfaz son *minor*; cosméticos, *patch*.

## 7. Dependencias

`game.toml` declara dependencias (`std = ">=0.3, <0.4"`, `juanma/tricktaking = "^1.2"`);
`game.lock` fija versiones y hashes. Resolución tipo cargo/npm.

```toml
[game]
id = "wizard"
version = "1.0.0"
authors = ["…"]
license = "CC-BY-4.0"
players = "3..6"
tags = ["cartas", "bazas", "apuestas"]

[dependencies]
std = ">=0.3, <0.4"
```

## 8. Búsqueda por propiedades matemáticas

Como cada juego se clasifica automáticamente, se puede buscar: *"2 jugadores, suma cero,
información perfecta, ramificación < 10"*, *"cooperativos con información oculta"*, *"juegos de
bazas para 4 con equipos"*. Etiquetas de autor + propiedades derivadas + tamaño estimado.

## 9. Partidas alojadas y comunidad

Salas online con código, emparejamiento, ratings humanos por juego/versión, torneos, perfiles,
organizaciones (clubes, asignaturas), estrellas, seguidores.

## 10. Propiedad intelectual (nota)

Las mecánicas de un juego suelen tratarse como ideas no protegibles, pero **el texto de un
reglamento, el arte y las marcas sí lo están** (p. ej. nombres comerciales de juegos publicados).
El catálogo oficial debería usar reglas redactadas por nosotros, arte propio y, si hace falta,
nombres genéricos. Antes de abrir el hub al público conviene una revisión legal.

## 11. Etapas

| Etapa | Contenido |
|---|---|
| **v0** (Fase 2) | `game.toml`, dependencias, `clone`/`fork` sobre URLs git, `diff` semántico en CLI |
| **v1** (Fase 10) | Web: cuentas, repos, explorar, página del juego, jugar, publicar, registro |
| **v2** (Fase 10–12) | PRs con diffs semántico/visual/balance, arena, Pages, búsqueda por propiedades, árbol genealógico |
