// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { clientMessage, displayCode, isHidden, normalizeCode } from "../src";

describe("códigos de sala", () => {
  it("normaliza como el servidor", () => {
    expect(normalizeCode("k7f-q2p")).toBe("K7FQ2P");
    expect(normalizeCode(" K7F Q2P ")).toBe("K7FQ2P");
    expect(normalizeCode("oil-OIL")).toBe("011011");
  });

  it("rechaza lo que no es un código", () => {
    expect(normalizeCode("K7FQ2")).toBeNull();
    expect(normalizeCode("K7FQ2PX")).toBeNull();
    expect(normalizeCode("K7FQ2U")).toBeNull();
    expect(normalizeCode("")).toBeNull();
  });

  it("se muestra partido por la mitad", () => {
    expect(displayCode("K7FQ2P")).toBe("K7F-Q2P");
  });
});

describe("mensajes", () => {
  it("construye el sobre del cliente", () => {
    expect(clientMessage("ready", { ready: true }, "a1-1")).toEqual({
      v: 1,
      type: "ready",
      id: "a1-1",
      data: { ready: true },
    });
    expect(clientMessage("stand", {})).toEqual({ v: 1, type: "stand", data: {} });
  });

  it("reconoce los valores ocultos", () => {
    expect(isHidden({ $hidden: true })).toBe(true);
    expect(isHidden({ size: 3, items: [] })).toBe(false);
    expect(isHidden(null)).toBe(false);
    expect(isHidden("K")).toBe(false);
  });
});
