# GameHub Studio — editor visual

> Estado: **diseño v0.1** (Fase 0). Implementación prevista en la Fase 5; un visualizador de solo
> lectura llega antes (Fase 2).

## 1. Idea

Una aplicación web (se abre con `gamehub studio` en local, y más tarde en el hub) donde el juego
se diseña **como diagrama de flujo**, **como texto** o **ambos a la vez**. Las dos vistas editan la
misma [GameIR](ir.md); cambiar una actualiza la otra al instante.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Wizard ▾   ● sin errores   ▶ Simular   ⎇ main   ⇪ Publicar                  │
├───────────────┬──────────────────────────────────────┬─────────────────────┤
│ EXPLORADOR    │  DIAGRAMA  ◫  TEXTO                  │ INSPECTOR           │
│ ▸ Estado      │   ┌─────────┐    ┌──────────────┐    │ Nodo: Bid           │
│ ▸ Componentes │   │ chance  │───►│ decision Bid │    │ tipo: decision      │
│ ▸ Funciones   │   │ Deal    │    └──────┬───────┘    │ actor: next(dealer) │
│ ▸ Flow        │   └─────────┘   todos   │ apostado   │ acciones:           │
│   ▸ Round     │                         ▼            │  bid(n: 0..round)   │
│     Deal      │                 ┌──────────────┐     │ transiciones (orden)│
│     Bid       │                 │ phase Trick  │     │  → Trick si …       │
│     Trick     │                 └──────────────┘     │  → Bid              │
├───────────────┴──────────────────────────────────────┴─────────────────────┤
│ SIMULADOR · vista de: [Asiento 0 ▾] [Omnisciente]   ◀◀ ◀ ▶ ▶▶  paso 37/112 │
│ eventos · estado · acciones legales · problemas (2)                         │
└────────────────────────────────────────────────────────────────────────────┘
```

## 2. Lenguaje visual

| Elemento del modelo | Representación |
|---|---|
| `decision` | Rectángulo; icono de persona + expresión del actor |
| `simultaneous` | Rectángulo doble; icono de varias personas |
| `window` | Hexágono (ventana de reacción) con modo `priority` / `collect` / `race` |
| `chance` | Círculo con dado (el azar **se ve** en el diagrama) |
| `auto` | Rectángulo redondeado gris |
| `phase` | Contenedor (swimlane) plegable; bucles indicados en la cabecera |
| `call` | Rectángulo con doble barra lateral (sub-flow) |
| `terminal` | Doble círculo con el resumen de pagos |
| Transición | Flecha con etiqueta de guarda; número de orden de evaluación; efectos al pasar el ratón |
| Acción con destino propio | Flecha que sale de la acción (no del nodo) |

## 3. Funciones

**Diseño**
- Paleta de nodos con arrastrar y soltar; conexión de flechas; plegado de fases.
- Inspector con formularios para actor(es), acciones, parámetros (con dominio), guardas, efectos y
  visibilidad. Las expresiones se escriben en un mini-editor con autocompletado y comprobación de
  tipos en vivo (más adelante, opción de **bloques tipo Scratch/Blockly** para no programadores).
- Editor del **esquema de estado** (variables, zonas, tableros) con selector de visibilidad.
- **Diseñador de componentes:** barajas (producto de palos × valores + especiales), fichas, dados,
  tableros de rejilla o grafo (dibujar casillas y conexiones: Parchís).
- **Plantillas:** "juego de bazas", "carrera en tablero", "matriz 2×2", "subasta"… y la stdlib.
- Auto-layout con ELK; posiciones guardadas en el *sidecar* `.layout.json`.

**Verificación**
- Panel de problemas en vivo (`gamehub check`): tipos, nodos inalcanzables, transiciones no
  exhaustivas, bucles sin progreso, **fugas de información**.
- Clasificación automática del juego (información perfecta, azar, suma cero…) y tamaño estimado.

**Simulación y depuración**
- Jugar como cualquier asiento contra humanos, bots aleatorios o heurísticos.
- **Vistas lado a lado** de varios asientos + vista omnisciente → comprobar a ojo quién ve qué.
- Paso a paso, playouts aleatorios masivos, **puntos de ruptura** en nodos o condiciones,
  **viaje en el tiempo** (el estado es inmutable: cada paso se conserva).
- Resaltado en el diagrama del nodo activo y de las transiciones recorridas; mapa de calor de
  **cobertura de reglas** (qué nodos/acciones/guardas se han disparado en N partidas).
- Explorador de árbol para juegos pequeños.

**Colaboración (más adelante)**
- Diff visual entre versiones (nodos añadidos/eliminados/modificados coloreados).
- Edición colaborativa en tiempo real (CRDT, Yjs).
- Exportar el diagrama a SVG/PNG y el reglamento a Markdown/PDF.

## 4. Round-trip texto ↔ diagrama (el punto difícil)

- El diagrama **no** genera texto plantilla: ambos son proyecciones de la IR de autor.
- Editar en el diagrama produce un *patch* de IR → el formateador re-emite **solo** las regiones
  afectadas del texto, conservando comentarios y estilo.
- Editar el texto re-parsea (tolerante a errores) → la IR se actualiza → el diagrama se re-renderiza
  conservando posiciones por `id` de nodo.
- Test de propiedad obligatorio: `texto → IR → texto` es idempotente y `IR → texto → IR` es la
  identidad.

## 5. Implementación (propuesta)

React + `@xyflow/react` (lienzo) + ELK.js (layout) + Monaco (texto) + LSP de GameHub en Python
(`pygls`) servido por `gamehub studio` vía WebSocket. Motor de simulación: el de referencia en
Python a través del servidor local; más adelante el core en WASM para funcionar sin servidor.
