import { useState } from "react";
import type { CellKind, RepairResponse } from "../lib/types";
import { InspectPanel } from "./InspectPanel";

const KIND_LABEL: Record<CellKind, string> = {
  original_hole: "原孔（1→1）",
  added_hole: "补孔（0→1，纠正丢孔）",
  removed_hole: "改孔（1→0，纠正误孔）",
  kept_blank: "原空（0→0）",
  unknown_hole: "缺失定孔（?→1，不计改动）",
  unknown_blank: "缺失定空（?→0，不计改动）",
};

function cellSymbol(kind: CellKind): string {
  switch (kind) {
    case "original_hole":
      return "●";
    case "added_hole":
      return "◆";
    case "removed_hole":
      return "○";
    case "unknown_hole":
      return "◇";
    case "unknown_blank":
      return "·";
    case "kept_blank":
      return "·";
  }
}

export function ResultView({ result }: { result: RepairResponse }) {
  const changedCells = result.diff.flat().filter((c) => c.counts_as_change);
  const added = changedCells.filter((c) => c.kind === "added_hole").length;
  const removed = changedCells.filter((c) => c.kind === "removed_hole").length;
  // 核验时间线点选异常纬时，同时高亮修复矩阵对应基准纬与回读行。
  const [selectedRefPick, setSelectedRefPick] = useState<number | null>(null);
  const [selectedReadSeq, setSelectedReadSeq] = useState<number | null>(null);

  function handleSelect(refPick: number | null, readSeq: number | null) {
    setSelectedRefPick(refPick);
    setSelectedReadSeq(readSeq);
  }

  const legends: CellKind[] = [
    "original_hole",
    "added_hole",
    "removed_hole",
    "kept_blank",
    "unknown_hole",
    "unknown_blank",
  ];

  // 已批准修复矩阵的 0/1 行串，作为试打核验的基准。
  const matrixRows = result.matrix.map((row) => row.join(""));

  return (
    <section className="result" aria-label="修复结果">
      <h2>修复结果</h2>
      <div className="summary">
        <span className="changes" data-testid="changes-total">
          改动总数：<b>{result.changes}</b>
        </span>
        <span data-testid="changes-added">补孔 {added} 处</span>
        <span data-testid="changes-removed">改孔 {removed} 处</span>
        <span className="muted">
          每纬孔数 K={result.picks}，最大循环浮长 L={result.max_float}
        </span>
        <span className="muted">求解用时 {result.solve_seconds} s</span>
      </div>

      <ul className="legend">
        {legends.map((k) => (
          <li key={k} className={`legend-item kind-${k}`}>
            <span className="glyph">{cellSymbol(k)}</span>
            {KIND_LABEL[k]}
          </li>
        ))}
      </ul>

      <div className="tables">
        <div>
          <h3>修复后纹板（逐格差异着色）</h3>
          <table className="grid" data-testid="result-grid">
            <tbody>
              {result.diff.map((row, i) => (
                <tr
                  key={i}
                  id={`ref-row-${i + 1}`}
                  className={selectedRefPick === i + 1 ? "row-highlight" : ""}
                  data-ref-pick={i + 1}
                >
                  <th className="rownum">{i + 1}</th>
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className={`cell kind-${cell.kind}`}
                      title={KIND_LABEL[cell.kind]}
                      data-kind={cell.kind}
                      data-input={cell.input}
                      data-output={cell.output}
                    >
                      <span className="glyph">{cellSymbol(cell.kind)}</span>
                      <span className="bits">
                        {cell.input}→{cell.output}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h3>修复后 0/1 矩阵</h3>
          <table className="grid plain">
            <tbody>
              {result.matrix.map((row, i) => (
                <tr
                  key={i}
                  className={selectedRefPick === i + 1 ? "row-highlight" : ""}
                >
                  <th className="rownum">{i + 1}</th>
                  {row.map((bit, j) => (
                    <td key={j} className={bit === 1 ? "one" : "zero"}>
                      {bit}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <InspectPanel
        height={result.height}
        width={result.width}
        matrixRows={matrixRows}
        selectedRefPick={selectedRefPick}
        selectedReadSeq={selectedReadSeq}
        onSelect={handleSelect}
      />
    </section>
  );
}
