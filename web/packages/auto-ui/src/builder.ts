// SPDX-License-Identifier: Apache-2.0
/**
 * El constructor de acciones de la UI genérica: elige la acción y sus argumentos uno a uno, en
 * el orden en que se declaran, con los valores posibles que dicen las acciones legales
 * (enumeradas) o el servidor (`query_actions`, si son progresivas). Los argumentos que se eligen
 * tocando el tablero o una zona se marcan allí; el resto, con botones.
 *
 * Los valores posibles se calculan (o se piden) una sola vez por actualización. Para marcar varios
 * elementos de una zona con un dominio `subsets(items(Z), a, b)` no hace falta la lista de todos
 * los subconjuntos (pueden ser decenas de miles): con acciones progresivas basta con que la
 * selección tenga entre `a` y `b` elementos, y el servidor rechaza lo que no valga.
 */

import { canonicalJson, nextValues } from "@gamehub/client";
import type { ActionData, Legal, View } from "@gamehub/protocol";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type ActionModel,
  type ActionParamModel,
  type GameModel,
  resolveBound,
  resolveSeat,
} from "./ir";
import type { GridInteraction, PickInteraction } from "./values";
import { zoneItems } from "./values";

export interface BuilderOptions {
  model: GameModel;
  view: View;
  seat: number | null;
  legal: Legal | null;
  params: Record<string, unknown>;
  onAct?: (action: ActionData) => void;
  queryActions?: (name?: string, args?: Record<string, unknown>) => Promise<unknown[]>;
  /** Hay una jugada enviada sin respuesta: no se puede jugar otra. */
  busy?: boolean;
}

export interface Builder {
  /** Me toca y puedo jugar. */
  ready: boolean;
  actions: ActionModel[];
  chosen: ActionModel | null;
  args: Record<string, unknown>;
  /** El argumento que toca elegir de la acción elegida. */
  current: ActionParamModel | null;
  /** Sus valores posibles (null mientras se piden al servidor). */
  candidates: unknown[] | null;
  /** Para elegir varios de una zona: lo marcado, si vale y cuántos se pueden elegir. */
  picked: number[];
  pickAction: ActionModel | null;
  pickValid: boolean;
  pickRange: [number | undefined, number | undefined] | null;
  choose: (name: string) => void;
  setValue: (value: unknown) => void;
  confirmPick: () => void;
  cancel: () => void;
  /** Cómo se puede tocar la rejilla `name` ahora (null si no se puede). */
  grid: (name: string) => GridInteraction | null;
  /** Cómo se pueden marcar los elementos de la zona `name` del asiento `seat`. */
  pick: (name: string, seat: number | null) => PickInteraction | null;
  /** Qué hay que hacer ahora, para mostrárselo a quien juega. */
  step: Step | null;
}

export type Step =
  | { kind: "board"; input: "cell" | "column" | "row" }
  | { kind: "pick"; zone: string; many: boolean; action: ActionModel }
  | { kind: "choice"; param: ActionParamModel; action: ActionModel }
  | { kind: "actions" };

const PASS: ActionModel = { name: "pass", label: "pass", params: [] };

function actionFor(
  model: GameModel,
  node: string | null,
  name: string,
  sample?: ActionData,
): ActionModel {
  const found = node === null ? undefined : model.nodes.get(node)?.actions.get(name);
  if (found) return found;
  if (name === "pass") return PASS;
  // Una acción que la IR no declara en este nodo: sus argumentos, con botones.
  return {
    name,
    label: name,
    params: Object.keys(sample?.args ?? {}).map((p) => ({
      name: p,
      type: { kind: "unknown" },
      label: p,
      input: { kind: "choice" },
    })),
  };
}

/** Los valores posibles de un argumento, con sus claves canónicas para comprobar pertenencia. */
interface Options {
  values: unknown[];
  keys: Set<string>;
  /** Para listas de elementos (elegir varios): las claves de los elementos que aparecen. */
  items?: Set<string>;
}

const NO_OPTIONS: Options = { values: [], keys: new Set() };

function optionsOf(values: unknown[]): Options {
  return { values, keys: new Set(values.map((v) => canonicalJson(v))) };
}

function itemKeys(options: Options): Set<string> {
  if (options.items === undefined) {
    const items = new Set<string>();
    for (const option of options.values) {
      if (Array.isArray(option)) for (const item of option) items.add(canonicalJson(item));
    }
    options.items = items;
  }
  return options.items;
}

/** Clave de una selección: ordenada si el argumento es un conjunto. */
function selectionKey(values: unknown[], unordered: boolean): string {
  if (!unordered) return canonicalJson(values);
  return canonicalJson(values.map((v) => canonicalJson(v)).sort());
}

interface Store {
  legal: Legal | null;
  map: Map<string, Options | "loading">;
  /** Claves de las selecciones válidas de cada argumento de elegir varios (sin orden si es un
   * conjunto). */
  selections: Map<string, Set<string>>;
}

export function useActionBuilder(o: BuilderOptions): Builder {
  const { model, view, legal, seat, params, onAct, queryActions } = o;
  const [chosenName, setChosen] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, unknown>>({});
  const [picked, setPicked] = useState<number[]>([]);
  const [, setVersion] = useState(0);
  const store = useRef<Store>({ legal, map: new Map(), selections: new Map() });
  if (store.current.legal !== legal) {
    store.current = { legal, map: new Map(), selections: new Map() };
  }
  const legalRef = useRef(legal);

  // Cada actualización nueva empieza de cero.
  useEffect(() => {
    if (legalRef.current !== legal) {
      legalRef.current = legal;
      setChosen(null);
      setArgs({});
      setPicked([]);
    }
  }, [legal]);

  const ready = legal !== null && !o.busy && seat !== null;
  const actions = useMemo(() => {
    if (legal === null) return [];
    if (legal.kind === "enumerated") {
      const seen = new Map<string, ActionData>();
      for (const a of legal.actions) if (!seen.has(a.name)) seen.set(a.name, a);
      return [...seen.entries()].map(([name, sample]) => actionFor(model, view.node, name, sample));
    }
    return legal.names.map((name) => actionFor(model, view.node, name));
  }, [legal, model, view.node]);

  /** Valores posibles del argumento `param` de `name` tras `prefix` (null: preguntando). */
  const options = (
    name: string,
    prefix: Record<string, unknown>,
    param: string,
  ): Options | null => {
    if (legal === null) return NO_OPTIONS;
    const current = store.current;
    const k = canonicalJson([name, prefix, param]);
    const found = current.map.get(k);
    if (found === "loading") return null;
    if (found !== undefined) return found;
    if (legal.kind === "enumerated") {
      const computed = optionsOf(nextValues(legal.actions, name, prefix, param));
      current.map.set(k, computed);
      return computed;
    }
    if (queryActions === undefined) return NO_OPTIONS;
    current.map.set(k, "loading");
    queryActions(name, prefix).then(
      (values) => {
        current.map.set(k, optionsOf(values));
        if (store.current === current) setVersion((n) => n + 1);
      },
      () => {
        current.map.set(k, NO_OPTIONS);
        if (store.current === current) setVersion((n) => n + 1);
      },
    );
    return null;
  };

  const reset = () => {
    setChosen(null);
    setArgs({});
    setPicked([]);
  };

  const send = (action: ActionModel, full: Record<string, unknown>) => {
    onAct?.({ name: action.name, args: full });
    reset();
  };

  /** Fija un argumento de `action` y, si ya están todos, juega. */
  const bind = (
    action: ActionModel,
    prefix: Record<string, unknown>,
    param: string,
    value: unknown,
  ) => {
    const next = { ...prefix, [param]: value };
    setPicked([]);
    if (action.params.every((p) => p.name in next)) {
      send(action, next);
    } else {
      setChosen(action.name);
      setArgs(next);
    }
  };

  const chosen = chosenName === null ? null : (actions.find((a) => a.name === chosenName) ?? null);
  const current = chosen ? (chosen.params.find((p) => !(p.name in args)) ?? null) : null;
  const currentCandidates =
    chosen && current ? (options(chosen.name, args, current.name)?.values ?? null) : null;

  const zoneValues = (name: string, zoneSeat: number | null): unknown[] => {
    const v = model.vars.find((x) => x.name === name);
    const raw = view.state[name];
    const value = v?.perPlayer && Array.isArray(raw) ? raw[zoneSeat ?? -1] : raw;
    return zoneItems(value).items;
  };

  // La acción cuyo argumento se elige marcando varios elementos de una zona (p. ej. cartas).
  const pickTarget = (() => {
    if (!ready) return null;
    if (chosen && current) {
      return current.input.kind === "pick" && current.input.many
        ? { action: chosen, param: current, prefix: args }
        : null;
    }
    for (const a of actions) {
      const first = a.params[0];
      if (first?.input.kind === "pick" && first.input.many) {
        return { action: a, param: first, prefix: {} as Record<string, unknown> };
      }
    }
    return null;
  })();

  const pickRange: [number | undefined, number | undefined] | null = pickTarget
    ? [
        resolveBound(pickTarget.param.input.min, params),
        resolveBound(pickTarget.param.input.max, params),
      ]
    : null;
  // Con acciones progresivas y un dominio con tamaños, basta con comprobar el tamaño.
  const bySize =
    pickTarget !== null &&
    legal?.kind === "progressive" &&
    (pickRange?.[0] !== undefined || pickRange?.[1] !== undefined);

  const pickedValues = (() => {
    if (!pickTarget) return null;
    const zoneSeat = resolveSeat(pickTarget.param.input.seat, seat, view.state);
    const items = zoneValues(pickTarget.param.input.of ?? "", zoneSeat);
    return [...picked].sort((a, b) => a - b).map((i) => items[i]);
  })();

  const pickValid = (() => {
    if (!pickTarget || !pickedValues || pickedValues.length === 0) return false;
    if (bySize) {
      const [lo, hi] = pickRange ?? [undefined, undefined];
      return (
        (lo === undefined || pickedValues.length >= lo) &&
        (hi === undefined || pickedValues.length <= hi)
      );
    }
    const found = options(pickTarget.action.name, pickTarget.prefix, pickTarget.param.name);
    if (found === null) return false;
    const unordered = pickTarget.param.type.kind === "set";
    const k = canonicalJson([pickTarget.action.name, pickTarget.prefix, pickTarget.param.name]);
    let valid = store.current.selections.get(k);
    if (valid === undefined) {
      valid = new Set(found.values.map((v) => selectionKey(Array.isArray(v) ? v : [v], unordered)));
      store.current.selections.set(k, valid);
    }
    return valid.has(selectionKey(pickedValues, unordered));
  })();

  const choose = useCallback(
    (name: string) => {
      const action = actions.find((a) => a.name === name);
      if (!action || !ready) return;
      if (action.params.length === 0) {
        onAct?.({ name: action.name, args: {} });
        setChosen(null);
        setArgs({});
        setPicked([]);
        return;
      }
      setChosen(name);
      setArgs({});
      setPicked([]);
    },
    [actions, ready, onAct],
  );

  const setValue = (value: unknown) => {
    if (chosen && current) bind(chosen, args, current.name, value);
  };

  const confirmPick = () => {
    if (pickTarget && pickValid && pickedValues) {
      bind(pickTarget.action, pickTarget.prefix, pickTarget.param.name, pickedValues);
    }
  };

  /** Las acciones (y su argumento) que ahora se eligen tocando la variable `name`. */
  const inputsOn = (name: string, kinds: string[]) => {
    if (!ready) return [];
    if (chosen && current) {
      return current.input.of === name && kinds.includes(current.input.kind)
        ? [{ action: chosen, param: current, prefix: args }]
        : [];
    }
    return actions.flatMap((a) => {
      const first = a.params[0];
      return first && first.input.of === name && kinds.includes(first.input.kind)
        ? [{ action: a, param: first, prefix: {} as Record<string, unknown> }]
        : [];
    });
  };

  const grid = (name: string): GridInteraction | null => {
    const inputs = inputsOn(name, ["cell", "column", "row"]);
    if (inputs.length === 0) return null;
    const mode = inputs[0]?.param.input.kind as "cell" | "column" | "row";
    const found = inputs.map((x) => ({
      ...x,
      keys: options(x.action.name, x.prefix, x.param.name)?.keys ?? new Set<string>(),
    }));
    const valueAt = (r: number, c: number) =>
      mode === "cell" ? [r, c] : mode === "column" ? c : r;
    return {
      mode,
      isTarget: (r, c) => found.some((x) => x.keys.has(canonicalJson(valueAt(r, c)))),
      onSelect: (r, c) => {
        const value = valueAt(r, c);
        const hit = found.find((x) => x.keys.has(canonicalJson(value)));
        if (hit) bind(hit.action, hit.prefix, hit.param.name, value);
      },
    };
  };

  const pick = (name: string, zoneSeat: number | null): PickInteraction | null => {
    const inputs = inputsOn(name, ["pick"]).filter(
      (x) => resolveSeat(x.param.input.seat, seat, view.state) === zoneSeat,
    );
    if (inputs.length === 0) return null;
    const items = zoneValues(name, zoneSeat);
    const many = inputs.find((x) => x.param.input.many);
    if (many) {
      const max = resolveBound(many.param.input.max, params);
      const usable = bySize
        ? null
        : itemKeys(options(many.action.name, many.prefix, many.param.name) ?? NO_OPTIONS);
      return {
        isSelectable: (i) => usable === null || usable.has(canonicalJson(items[i])),
        isSelected: (i) => picked.includes(i),
        toggle: (i) =>
          setPicked((now) =>
            now.includes(i)
              ? now.filter((x) => x !== i)
              : max !== undefined && now.length >= max
                ? [...now.slice(1), i]
                : [...now, i],
          ),
      };
    }
    const found = inputs.map((x) => ({
      ...x,
      keys: options(x.action.name, x.prefix, x.param.name)?.keys ?? new Set<string>(),
    }));
    return {
      isSelectable: (i) => found.some((x) => x.keys.has(canonicalJson(items[i]))),
      isSelected: () => false,
      toggle: (i) => {
        const hit = found.find((x) => x.keys.has(canonicalJson(items[i])));
        if (hit) bind(hit.action, hit.prefix, hit.param.name, items[i]);
      },
    };
  };

  const step: Step | null = (() => {
    if (!ready) return null;
    if (chosen && current) {
      const input = current.input;
      if (input.kind === "cell" || input.kind === "column" || input.kind === "row") {
        return { kind: "board", input: input.kind };
      }
      if (input.kind === "pick") {
        return { kind: "pick", zone: input.of ?? "", many: input.many ?? false, action: chosen };
      }
      return { kind: "choice", param: current, action: chosen };
    }
    const first = actions.map((a) => a.params[0]).find((p) => p && p.input.kind !== "choice");
    if (first && first.input.kind !== "pick" && first.input.kind !== "choice") {
      return { kind: "board", input: first.input.kind };
    }
    if (pickTarget) {
      return {
        kind: "pick",
        zone: pickTarget.param.input.of ?? "",
        many: true,
        action: pickTarget.action,
      };
    }
    return { kind: "actions" };
  })();

  return {
    ready,
    actions,
    chosen,
    args,
    current,
    candidates: currentCandidates,
    picked,
    pickAction: pickTarget?.action ?? null,
    pickValid,
    pickRange,
    choose,
    setValue,
    confirmPick,
    cancel: reset,
    grid,
    pick,
    step,
  };
}
