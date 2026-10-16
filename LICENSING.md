# Licencias de GameHub

| Parte del repositorio | Licencia | Archivo |
|---|---|---|
| Todo, salvo lo indicado abajo (motor, lenguaje Nomos, especificaciones, SDKs, herramientas, documentación) | Apache-2.0 | [`LICENSE`](LICENSE) |
| Servidor del hub (`hub/`, cuando exista) | AGPL-3.0-or-later | `hub/LICENSE` (se añadirá en la Fase 10) |
| Contenido de los juegos oficiales en `games/` (reglas, textos, arte) | CC-BY-4.0 | [`games/LICENSE.md`](games/LICENSE.md) |
| Código de las interfaces de los juegos en `games/*/ui/` | Apache-2.0 | [`LICENSE`](LICENSE) |

- Cada archivo de código fuente lleva su identificador SPDX en la cabecera
  (`SPDX-License-Identifier: Apache-2.0`).
- Los juegos publicados por terceros en el hub llevan la licencia que elija su autor
  (recomendada: CC-BY-4.0).
- Decisión registrada en [ADR-016](docs/wiki/decisiones.md).

## Dependencias de terceros en las apps web

Las apps compiladas (`web/apps/*/dist`, que también viajan en la rueda de Python) incluyen
dependencias con sus propias licencias, sin modificar: React, React Flow (`@xyflow/react`),
CodeMirror y `marked` (MIT), y **elkjs (EPL-2.0)**, la disposición automática del Studio, cuyo
código fuente está en <https://github.com/kieler/elkjs>. Las versiones exactas están en
`pnpm-lock.yaml`.

Copyright 2026 Juan Martin Fajardo y colaboradores de GameHub.
