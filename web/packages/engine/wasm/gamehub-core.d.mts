// TypeScript bindings for emscripten-generated code.  Automatically generated at compile time.
interface WasmModule {
}

type EmbindString = ArrayBuffer|Uint8Array|Uint8ClampedArray|Int8Array|string;
export interface ClassHandle {
  isAliasOf(other: ClassHandle): boolean;
  delete(): void;
  deleteLater(): this;
  isDeleted(): boolean;
  // @ts-ignore - If targeting lower than ESNext, this symbol might not exist.
  [Symbol.dispose](): void;
  clone(): this;
}
export interface Game extends ClassHandle {
  error(): string;
  usesNatives(): boolean;
  id(): string;
  title(): string;
  rulesHash(): string;
  minPlayers(): number;
  maxPlayers(): number;
  playouts(_0: number, _1: EmbindString, _2: number, _3: number, _4: number): string;
  studioPlayouts(_0: number, _1: EmbindString, _2: number, _3: number, _4: number, _5: number): string;
}

export interface Session extends ClassHandle {
  error(): string;
  status(): string;
  node(): string;
  depth(): number;
  activeSeats(): string;
  view(_0: number): string;
  eventsFrom(_0: number, _1: number): string;
  snapshot(): string;
  digest(): string;
  payoffs(): string;
  ranking(): string;
  legal(_0: number, _1: number): string;
  options(_0: number, _1: EmbindString, _2: EmbindString): string;
  act(_0: number, _1: EmbindString): string;
  chance(): string;
  applyChance(_0: EmbindString): string;
  chanceOutcomes(_0: number): string;
  undo(): boolean;
  botAction(_0: number, _1: EmbindString, _2: number, _3: number): string;
}

interface EmbindModule {
  Game: {
    new(_0: EmbindString, _1: boolean): Game;
  };
  Session: {
    new(_0: Game, _1: number, _2: EmbindString, _3: number): Session;
  };
  OMNISCIENT: number;
  PUBLIC: number;
}

export type MainModule = WasmModule & EmbindModule;
export default function MainModuleFactory (options?: unknown): Promise<MainModule>;
