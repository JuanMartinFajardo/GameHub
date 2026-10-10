# gamehub (paquete Python)

Herramientas de GameHub en Python: el lenguaje **Nomos** (compilador, formateador, tests,
análisis), la GameIR, el motor de referencia y, desde la Fase 3, el **servidor de partidas**,
el SDK cliente y el juego en red desde la terminal.

```bash
uv sync                                          # entorno de desarrollo
uv run pytest                                    # tests (los de LAN/mDNS: GAMEHUB_LAN_TESTS=1)
uv run gamehub check ../games                    # compilar y analizar los juegos
uv run gamehub test ../games                     # sus tests e invariantes
uv run gamehub play ../games/nim --seats human,random

uv run gamehub host ../games/dudo --players 4    # abrir una sala en la LAN y jugar
uv run gamehub join K7F-Q2P                      # unirse desde otro equipo
uv run gamehub bot run random --room K7F-Q2P     # un bot en la sala
uv run gamehub serve ../games                    # servidor de partidas (salas por la API)
```

Documentación del proyecto: [`docs/wiki`](../docs/wiki/README.md) (lenguaje, motor, protocolo).
