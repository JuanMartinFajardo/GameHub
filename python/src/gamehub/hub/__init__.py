# SPDX-License-Identifier: AGPL-3.0-or-later
"""El hub de GameHub ("GitHub para juegos", fase 10): repositorios git de juegos y librerías,
versiones con semver automático, forks, propuestas con diffs de texto, semántica, diagrama y
balance, juego en línea con valoraciones, búsqueda por propiedades y trabajos aislados.

- `service`: cuentas, organizaciones, permisos, repositorios, archivos, moderación.
- `registry`: versiones publicadas (compilar en un commit, hashes, semver, dependencias).
- `pulls`: propuestas de cambio y sus cuatro capas de diff.
- `jobs` y `worker`: la cola de trabajos y el proceso hijo que los ejecuta.
- `play`: catálogo de versiones para las salas, valoraciones humanas, emparejamiento.
- `explore`: búsqueda por propiedades matemáticas y árbol genealógico.
- `pages`: interfaces publicadas.
- `app`: la API HTTP, git por HTTP, OAuth y la web; `client`: la parte de la CLI.
"""

DEFAULT_PORT = 7430
