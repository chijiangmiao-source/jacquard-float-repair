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

// ---- 试打核验 ------------------------------------------------------------

export type InspectStatus =
  | "match" // 匹配
  | "hole_mismatch" // 孔位不符
  | "missing_pick" // 漏纬
  | "repeated_pick"; // 重纬

export interface InspectCell {
  ref: 0 | 1 | null;
  read: 0 | 1 | null;
  same: boolean;
}

export interface TimelineEntry {
  kind: "aligned" | "missing_pick" | "repeated_pick";
  status: InspectStatus;
  ref_pick: number | null; // 基准纬号（1 基）
  read_seq: number | null; // 回读采集序行号（1 基）
  ref_row: number[] | null;
  read_row: number[] | null;
  cells: InspectCell[];
  mismatch_count: number;
}

export interface InspectEvent {
  kind: "missing_pick" | "repeated_pick";
  ref_pick: number | null;
  read_seq: number | null;
}

export interface InspectResponse {
  ok: boolean;
  height: number;
  width: number;
  readback_rows: number;
  max_misses: number;
  direction: "forward" | "reverse";
  start_pick: number;
  score: number;
  event_count: number;
  miss_count: number;
  repeat_count: number;
  mismatch_picks: number;
  mismatch_cells: number;
  mapping: number[][];
  events: InspectEvent[];
  timeline: TimelineEntry[];
}

export interface InspectInput {
  matrix: string[];
  readback: string[];
  maxMisses: number;
}
