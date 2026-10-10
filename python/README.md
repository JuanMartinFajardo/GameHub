# gamehub (paquete Python)

Herramientas de GameHub en Python: el lenguaje **Nomos** (compilador, formateador, tests,
análisis), la GameIR, el motor de referencia, el **servidor de partidas** (que sirve también la
app web para jugar en el navegador), el SDK cliente, el juego en red desde la terminal y las
herramientas para hacer interfaces propias.

```bash
uv sync                                          # entorno de desarrollo
uv run pytest                                    # tests (los de LAN/mDNS: GAMEHUB_LAN_TESTS=1)
uv run gamehub check ../games                    # compilar y analizar los juegos
uv run gamehub test ../games                     # sus tests e invariantes
uv run gamehub play ../games/nim --seats human,random

uv run gamehub serve ../games --open             # servidor de partidas + app web en el navegador
uv run gamehub host ../games/dudo --players 4    # abrir una sala en la LAN y jugar
uv run gamehub join K7F-Q2P                      # unirse desde otro equipo (o abrir el enlace)
uv run gamehub bot run random --room K7F-Q2P     # un bot en la sala

uv run gamehub ui new ../games/nim               # una UI propia de React (games/nim/ui)
uv run gamehub sdk ts ../games/nim -o tipos.ts   # los tipos de TypeScript de un juego
```

La app web se compila con `pnpm install && pnpm build` en la raíz del repositorio; `gamehub serve`
y `gamehub host` la encuentran solos (y la rueda la lleva dentro si estaba compilada al
construirla).

Documentación del proyecto: [`docs/wiki`](../docs/wiki/README.md) (lenguaje, motor, protocolo,
cliente web).
