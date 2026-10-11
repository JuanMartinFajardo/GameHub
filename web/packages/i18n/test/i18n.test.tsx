// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  defineMessages,
  format,
  humanize,
  LocaleProvider,
  pickText,
  plural,
  translator,
  useLocale,
  useMessages,
} from "../src";

const messages = defineMessages(
  { hello: "Hola, {name}", turn: "Te toca" },
  { hello: "Hello, {name}", turn: "Your turn" },
);

describe("textos", () => {
  it("elige el idioma de un texto de la IR", () => {
    expect(pickText({ es: "Tres en raya", en: "Tic-tac-toe" }, "en")).toBe("Tic-tac-toe");
    expect(pickText({ es: "Dudo" }, "en")).toBe("Dudo");
    expect(pickText("Nim", "en")).toBe("Nim");
    expect(pickText(undefined, "es")).toBe("");
  });

  it("convierte nombres del código en nombres para personas", () => {
    expect(humanize("dice_left")).toBe("Dice left");
    expect(humanize("TicTacToe")).toBe("Tic tac toe");
    expect(humanize("max_play")).toBe("Max play");
  });

  it("rellena variables y elige plurales", () => {
    expect(format("{a} y {b} y {c}", { a: 1, b: "dos" })).toBe("1 y dos y {c}");
    expect(translator(messages, "en")("hello", { name: "Ana" })).toBe("Hello, Ana");
    expect(plural("es", 1, "carta", "cartas")).toBe("carta");
    expect(plural("es", 3, "carta", "cartas")).toBe("cartas");
  });
});

function Greeting() {
  const t = useMessages(messages);
  const { locale, setLocale } = useLocale();
  return (
    <button type="button" onClick={() => setLocale(locale === "es" ? "en" : "es")}>
      {t("hello", { name: "Ana" })}
    </button>
  );
}

describe("idioma de la interfaz", () => {
  it("cambia al vuelo y se recuerda", () => {
    render(
      <LocaleProvider initial="es">
        <Greeting />
      </LocaleProvider>,
    );
    expect(screen.getByRole("button").textContent).toBe("Hola, Ana");
    act(() => screen.getByRole("button").click());
    expect(screen.getByRole("button").textContent).toBe("Hello, Ana");
    expect(localStorage.getItem("gamehub:locale")).toBe("en");
  });
});
