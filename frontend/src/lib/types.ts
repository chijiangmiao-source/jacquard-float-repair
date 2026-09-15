export type CellKind =
  | "original_hole" // 原孔：输入 1，结果仍 1
  | "added_hole" // 补孔（纠正丢孔）：输入 0，结果 1
  | "removed_hole" // 改孔（纠正误孔）：输入 1，结果 0
  | "kept_blank" // 原空保留：输入 0，结果 0
  | "unknown_hole" // ? 定为孔（不计改动）
  | "unknown_blank"; // ? 定为空（不计改动）

export interface DiffCell {
  input: string;
  output: 0 | 1;
  kind: CellKind;
  counts_as_change: boolean;
}

export interface RepairResponse {
  ok: boolean;
  height: number;
  width: number;
  picks: number;
  max_float: number;
  matrix: number[][];
  diff: DiffCell[][];
  changes: number;
  solve_seconds: number;
}

export interface ErrorResponse {
  ok: false;
  errors: string[];
  infeasible?: boolean;
}

export interface RepairInput {
  height: number;
  width: number;
  picks: number;
  maxFloat: number;
  rows: string[];
}
