# GameHub — instrucciones para Claude

## Idioma
- Comunicación y documentación en **español**. Código, identificadores y palabras clave del
  lenguaje `.game` en inglés.

## Mantenimiento obligatorio (petición explícita del usuario)
- Al terminar cualquier bloque de trabajo:
  1. Añadir una entrada **arriba** en `log.md` (fecha, qué se hizo, decisiones, siguientes pasos, % de progreso).
  2. Actualizar la wiki en `docs/wiki/`: el "Estado del proyecto" de `docs/wiki/README.md`, los
     checkboxes de `docs/wiki/roadmap.md` y las páginas afectadas.
  3. Registrar decisiones de arquitectura en `docs/wiki/decisiones.md` (formato ADR) y mover las
     preguntas respondidas de `docs/wiki/preguntas-abiertas.md` a "Respondidas".

## Prioridades del proyecto
1. Diseñar juegos: lenguaje `.game` + editor visual (Studio), todo muy modular.
2. Jugar: servidor/protocolo + UIs que se conectan a los endpoints (local, LAN, online).
3. Después: catálogo, teoría de juegos, core C++, heurísticas, hub web.
4. Lo último: IA (RL, Deep RL, LLM).

## Comandos (desde `python/`)
- `uv run pytest` · `uv run ruff check .` · `uv run ruff format .` · `uv run pyright`
- `uv run gamehub ir check ../spec/ir/examples/*.ir.json` (validar IR)
- `uv run gamehub ir schemas --write` tras tocar `spec/ir/v0/ops.json` (los esquemas expr/stmt se generan)
- `uv run gamehub conformance --write` tras cambiar la semántica del motor o un ejemplo (y explicar
  por qué en el commit: las trazas son el contrato con otros motores)
- `uv run gamehub play|fuzz|replay …` (ver `docs/wiki/motor.md`)
- Separadores de comentario `# --- Título ---…` de 100 columnas como máximo (ruff E501).

## Git (política acordada el 2026-10-09)
- **Un commit por tarea terminada**, con mensaje en español y el trailer de coautoría.
- `main` contiene lo aprobado. Cada fase se trabaja en su rama (`f1/motor-referencia`, …) y se
  fusiona a `main` solo con el visto bueno del usuario. Nunca hacer push sin que lo pida.
- Antes de cada commit: tests, `ruff`, `pyright` y `gamehub ir check` en verde.

## Referencias
- Semántica: `docs/wiki/modelo-formal.md` · Sintaxis: `docs/wiki/lenguaje-game.md` ·
  IR: `docs/wiki/ir.md` · Arquitectura: `docs/wiki/arquitectura.md` · Roadmap: `docs/wiki/roadmap.md`.
- `structure.py` es el prototipo original del usuario: no modificarlo (análisis en
  `docs/wiki/analisis-structure-py.md`).
