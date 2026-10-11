// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  actionKey,
  canonicalJson,
  endpoints,
  matching,
  nextValues,
  roomTarget,
  sameAction,
} from "../src";

describe("direcciones", () => {
  it("entiende las mismas formas que el SDK de Python", () => {
    expect(endpoints("192.168.1.20")).toEqual({
      http: "http://192.168.1.20:7420",
      ws: "ws://192.168.1.20:7420/ws",
      code: null,
    });
    expect(endpoints("host:8000").http).toBe("http://host:8000");
    expect(endpoints("http://host:7420/r/k7fq2p").code).toBe("K7FQ2P");
    expect(endpoints("ws://host:7420/ws").http).toBe("http://host:7420");
    expect(endpoints("https://juegos.example.org")).toEqual({
      http: "https://juegos.example.org",
      ws: "wss://juegos.example.org/ws",
      code: null,
    });
    expect(endpoints("http://[::1]:7420").ws).toBe("ws://[::1]:7420/ws");
    expect(endpoints("http://host:80").http).toBe("http://host");
  });

  it("rechaza lo que no es un servidor", () => {
    expect(() => endpoints("ftp://host")).toThrow(/no válida/);
    expect(() => endpoints("http://")).toThrow(/no válida/);
  });

  it("separa servidor y código de lo que escribe alguien", () => {
    expect(roomTarget("k7f-q2p", "host:7420")).toEqual({
      server: "http://host:7420",
      code: "K7FQ2P",
    });
    expect(roomTarget("http://10.0.0.2:7420/r/K7FQ2P")).toEqual({
      server: "http://10.0.0.2:7420",
      code: "K7FQ2P",
    });
    expect(() => roomTarget("http://host:7420/")).toThrow(/código/);
    expect(() => roomTarget("nope")).toThrow(/no válido/);
  });
});

describe("acciones legales", () => {
  const legal = [
    { name: "bid", args: { q: 1, f: 2 } },
    { name: "bid", args: { q: 1, f: 3 } },
    { name: "bid", args: { q: 2, f: 2 } },
    { name: "dudo", args: {} },
  ];

  it("compara acciones sin importar el orden de las claves", () => {
    expect(canonicalJson({ b: 1, a: [{ d: 2, c: 3 }] })).toBe('{"a":[{"c":3,"d":2}],"b":1}');
    expect(
      sameAction({ name: "x", args: { a: 1, b: 2 } }, { name: "x", args: { b: 2, a: 1 } }),
    ).toBe(true);
    expect(actionKey({ name: "x", args: {} })).toBe('["x",{}]');
  });

  it("construye una acción argumento a argumento", () => {
    expect(nextValues(legal, "bid", {}, "q")).toEqual([1, 2]);
    expect(nextValues(legal, "bid", { q: 1 }, "f")).toEqual([2, 3]);
    expect(matching(legal, "bid", { q: 2, f: 2 })).toHaveLength(1);
    expect(matching(legal, "dudo")).toEqual([{ name: "dudo", args: {} }]);
    expect(matching(legal, "bid", { q: 9 })).toEqual([]);
  });
});
