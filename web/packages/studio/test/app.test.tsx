// SPDX-License-Identifier: Apache-2.0
/**
 * La app entera (`StudioApp`) contra `gamehub studio` de verdad, manejada como una persona: abrir
 * un juego, añadir un nodo desde la paleta, renombrarlo en el inspector, escribir en el texto y
 * ver el diagrama al día, y jugar en el simulador pulsando las casillas.
 */

import { LocaleProvider } from "@gamehub/i18n";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { StudioApp } from "../src/StudioApp";
import type { Studio } from "../src/store";
import { connectStudio, type RunningStudio, serverAvailable, startStudio } from "./studio";

// Los mensajes del servidor llegan fuera de act(): React no debe quejarse por ello.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;

let server: RunningStudio;
let studio: Studio;

const text = () => studio.editor?.state.doc.toString() ?? "";
const box = (container: HTMLElement, name: string) =>
  container.querySelector(`.react-flow__node[data-id="n:${name}"]`);

describe.skipIf(!serverAvailable)("la app del Studio", () => {
  beforeAll(async () => {
    server = await startStudio(["tictactoe"]);
    studio = await connectStudio(server);
  }, 90_000);

  afterAll(async () => {
    studio?.connection.close();
    await server?.stop();
  });

  it("del diagrama al texto, del texto al diagrama y a jugar", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <LocaleProvider initial="es">
        <StudioApp studio={studio} />
      </LocaleProvider>,
    );
    // Abrir el juego desde la lista de archivos: se dibuja el diagrama.
    await user.click(await screen.findByTitle("tictactoe/tictactoe.game"));
    await waitFor(() => expect(box(container, "Move")).not.toBeNull(), { timeout: 15_000 });
    expect(box(container, "Win")).not.toBeNull();
    expect(screen.getByText("✓ Compila")).toBeTruthy();

    // La paleta añade un final; queda seleccionado y el inspector lo enseña.
    const palette = screen.getByRole("toolbar", { name: "Nodos" });
    await user.click(within(palette).getByRole("button", { name: /final/ }));
    await waitFor(() => expect(text()).toContain("terminal End { payoff: fill(0) }"));
    await waitFor(() => expect(box(container, "End")).not.toBeNull());
    const inspector = screen.getByRole("complementary", { name: "Inspector" });
    const name = await within(inspector).findByDisplayValue("End");
    // Renombrarlo en el inspector cambia el texto.
    await user.clear(name);
    await user.type(name, "Tie{Enter}");
    await waitFor(() => expect(text()).toContain("terminal Tie { payoff: fill(0) }"));
    await waitFor(() => expect(box(container, "Tie")).not.toBeNull());
    expect(screen.getByTitle("Sin guardar")).toBeTruthy();

    // Escribir en el texto: el diagrama se pone al día.
    const view = studio.editor;
    if (!view) throw new Error("sin editor");
    const at = text().indexOf("    terminal Win");
    view.dispatch({
      changes: { from: at, insert: "    terminal Abandon { payoff: fill(0) }\n\n" },
    });
    await waitFor(() => expect(box(container, "Abandon")).not.toBeNull(), { timeout: 10_000 });

    // Seleccionar un nodo en el esquema de la izquierda lo abre en el inspector.
    await user.click(
      within(screen.getByRole("complementary", { name: "Juegos" })).getByText("Win"),
    );
    await waitFor(() => expect(within(inspector).getByDisplayValue("Win")).toBeTruthy());

    // A jugar: el simulador enseña el tablero de cada asiento; se juega pulsando casillas.
    await user.click(screen.getByRole("button", { name: /Simular/ }));
    await waitFor(() => expect(studio.getState().sim).not.toBeNull());
    const cells = await waitFor(() => {
      const found = container.querySelectorAll<HTMLElement>(".gh-sd-view.is-active .gh-grid__hit");
      expect(found.length).toBe(9);
      return found;
    });
    await user.click(cells[4] as HTMLElement);
    await waitFor(() => expect(studio.getState().sim?.snapshot.index).toBe(1));
    // Viaje en el tiempo: atrás.
    await user.click(screen.getByTitle("Atrás"));
    await waitFor(() => expect(studio.getState().sim?.snapshot.index).toBe(0));

    // Análisis: el asesor recomienda resolverlo; resolverlo da tablas.
    await user.click(screen.getByRole("tab", { name: "Análisis" }));
    await user.click(screen.getByRole("button", { name: "Viabilidad" }));
    const advice = await screen.findByRole("region", { name: "Viabilidad" }, { timeout: 60_000 });
    expect(within(advice).getByText(/alfa-beta/)).toBeTruthy();
    await user.click(within(advice).getByRole("button", { name: "Calcular" }));
    const solved = await screen.findByRole("region", { name: "Resolver" }, { timeout: 60_000 });
    expect(within(solved).getByText("Valor: (0, 0)")).toBeTruthy();
    expect(within(solved).getByText(/5\.?478 posiciones/)).toBeTruthy();
  }, 180_000);
});
