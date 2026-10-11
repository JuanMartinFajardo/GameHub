// SPDX-License-Identifier: Apache-2.0
import kuhn from "../../../../spec/ir/examples/kuhn-poker.ir.json";
import mentiroso from "../../../../spec/ir/examples/mentiroso.ir.json";
import nim from "../../../../spec/ir/examples/nim.ir.json";
import rps from "../../../../spec/ir/examples/rock-paper-scissors.ir.json";
import tictactoe from "../../../../spec/ir/examples/tictactoe.ir.json";
import type { GameIr } from "../src";

export const IR = {
  kuhn: kuhn as unknown as GameIr,
  mentiroso: mentiroso as unknown as GameIr,
  nim: nim as unknown as GameIr,
  rps: rps as unknown as GameIr,
  tictactoe: tictactoe as unknown as GameIr,
};

export const PLAYERS = [
  { seat: 0, name: "Ana" },
  { seat: 1, name: "Luis" },
  { seat: 2, name: "Eva" },
];
