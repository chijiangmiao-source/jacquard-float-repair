import { useEffect, useMemo, useState } from "react";
import { inspectMatrix, ApiError } from "../lib/api";
import type { InspectResponse, TimelineEntry } from "../lib/types";
import { validateInspectForm } from "../lib/validation";

interface Props {
  height: number;
  width: number;
  matrixRows: string[]; // 已批准修复矩阵的 0/1 行
  selectedRefPick: number | null;
  selectedReadSeq: number | null;
  onSelect: (refPick: number | null, readSeq: number | null) => void;
}

const STATUS_LABEL: Record<TimelineEntry["status"], string> = {
  match: "匹配",
  hole_mismatch: "孔位不符",
  missing_pick: "漏纬",
  repeated_pick: "重纬",
};

export function InspectPanel({
  height,
  width,
  matrixRows,
  selectedRefPick,
  selectedReadSeq,
  onSelect,
}: Props) {
  const [boundText, setBoundText] = useState("2");
  const [readbackText, setReadbackText] = useState(matrixRows.join("\n"));
  const [errors, setErrors] = useState<string[]>([]);
  const [inspect, setInspect] = useState<InspectResponse | null>(null);
  const [submittedRows, setSubmittedRows] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  // 新修复结果投入时（matrixRows 变化）重置本次核验的全部状态。
  useEffect(() => {
    setBoundText("2");
    setReadbackText(matrixRows.join("\n"));
    setErrors([]);
    setInspect(null);
    setSubmittedRows([]);
    onSelect(null, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matrixRows.join("\n")]);

  const live = useMemo(
    () =>
      validateInspectForm(
        { boundText, readbackText },
        height,
        width,
      ),
    [boundText, readbackText, height, width],
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    // 仅清除本次核验；修复结果由父级保留，不在此处触碰。
    setInspect(null);
    setErrors([]);
    onSelect(null, null);

    const { errors: vErrors, value } = live;
    if (vErrors.length > 0 || value === null) {
      // 实时提示区已展示同样信息，不重复弹错误框（避免同文出现两次）。
      return;
    }
    setLoading(true);
    try {
      const resp = await inspectMatrix({
        matrix: matrixRows,
        readback: value.readback,
        maxMisses: value.maxMisses,
      });
      setInspect(resp);
      setSubmittedRows(value.readback);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors([err.message]);
      } else {
        setErrors(["请求失败，请重试"]);
      }
    } finally {
      setLoading(false);
    }
  }

  function selectEntry(t: TimelineEntry) {
    onSelect(t.ref_pick, t.read_seq);
  }

  useEffect(() => {
    if (selectedRefPick === null) return;
    const el = document.getElementById(`ref-row-${selectedRefPick}`);
    el?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [selectedRefPick]);

  useEffect(() => {
    if (selectedReadSeq === null) return;
    const el = document.getElementById(`read-row-${selectedReadSeq}`);
    el?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [selectedReadSeq]);

  return (
    <section className="inspect" aria-label="试打核验">
      <h3>试打核验（设备回读对齐）</h3>
      <p className="muted inspect-hint">
        粘贴与修复矩阵<b>宽度一致</b>的 0/1 回读矩阵，选择 0～20 的送料错纬上限后
        发起试打核验。回读可从任意纬开始、正向或反向采集；系统以修复矩阵为基准做
        有界环形对齐，不重新求解、不改写纹板。
      </p>

      <form className="inspect-form" onSubmit={onSubmit} noValidate>
        <label className="bound-label">
          送料错纬上限（0–20）
          <input
            aria-label="送料错纬上限"
            inputMode="numeric"
            value={boundText}
            onChange={(e) => setBoundText(e.target.value)}
          />
        </label>
        <label className="rows-label">
          设备回读矩阵（每行一个等宽 0/1 字符串，可环形任意起点、正/反向）
          <textarea
            aria-label="设备回读矩阵"
            rows={6}
            spellCheck={false}
            value={readbackText}
            onChange={(e) => setReadbackText(e.target.value)}
          />
        </label>
        <div className="inspect-actions">
          <button type="submit" disabled={loading}>
            {loading ? "核验中…" : "发起试打核验"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setReadbackText(matrixRows.join("\n"))}
          >
            填入修复矩阵
          </button>
          {inspect !== null && (
            <button
              type="button"
              className="ghost"
              data-testid="clear-inspect"
              onClick={() => {
                setInspect(null);
                setErrors([]);
                onSelect(null, null);
              }}
            >
              清除本次核验
            </button>
          )}
        </div>
      </form>

      {live.errors.length > 0 && (
        <div className="hint" role="status" aria-label="核验录入提示">
          <ul>
            {live.errors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {errors.length > 0 && (
        <div className="errors inspect-errors" role="alert" aria-label="核验失败">
          <b>本次核验被拒绝（修复结果仍保留）：</b>
          <ul>
            {errors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {inspect !== null && (
        <InspectResultView
          inspect={inspect}
          readbackRows={submittedRows}
          selectedRefPick={selectedRefPick}
          selectedReadSeq={selectedReadSeq}
          onSelectEntry={selectEntry}
        />
      )}
    </section>
  );
}

function InspectResultView({
  inspect,
  readbackRows,
  selectedRefPick,
  selectedReadSeq,
  onSelectEntry,
}: {
  inspect: InspectResponse;
  readbackRows: string[];
  selectedRefPick: number | null;
  selectedReadSeq: number | null;
  onSelectEntry: (t: TimelineEntry) => void;
}) {
  const anomalies = inspect.timeline.filter((t) => t.status !== "match");
  return (
    <div className="inspect-result" data-testid="inspect-result">
      <div className="summary">
        <span data-testid="inspect-direction">
          采集方向：<b>{inspect.direction === "forward" ? "正向" : "反向"}</b>
        </span>
        <span data-testid="inspect-start">
          起始纬号：<b>{inspect.start_pick}</b>
        </span>
        <span data-testid="inspect-score">
          总分：<b>{inspect.score}</b>
        </span>
        <span data-testid="inspect-events">
          错纬事件：<b>{inspect.event_count}</b>（漏纬 {inspect.miss_count} /
          重纬 {inspect.repeat_count}）
        </span>
        <span data-testid="inspect-mismatch">
          孔位不符：<b>{inspect.mismatch_picks}</b> 纬 / {inspect.mismatch_cells} 孔
        </span>
        <span className={anomalies.length ? "verdict-bad" : "verdict-ok"}>
          {anomalies.length === 0 ? "核验通过：全部逐纬匹配" : "发现异常，请点选时间线定位"}
        </span>
      </div>

      <div className="inspect-body">
        <div className="timeline-wrap">
          <h4>对齐时间线（点选异常纬定位修复矩阵与回读行）</h4>
          <ol className="timeline" data-testid="inspect-timeline">
            {inspect.timeline.map((t, idx) => {
              const anomaly = t.status !== "match";
              const active =
                (t.ref_pick !== null && t.ref_pick === selectedRefPick) ||
                (t.read_seq !== null && t.read_seq === selectedReadSeq);
              return (
                <li key={idx}>
                  <button
                    type="button"
                    className={
                      "timeline-item"
                      + ` st-${t.status}`
                      + (anomaly ? " anomaly" : "")
                      + (active ? " active" : "")
                    }
                    data-testid={`timeline-${idx}`}
                    data-status={t.status}
                    data-ref-pick={t.ref_pick ?? ""}
                    data-read-seq={t.read_seq ?? ""}
                    onClick={() => onSelectEntry(t)}
                  >
                    <span className="t-badge">{idx + 1}</span>
                    <span className="t-status">{STATUS_LABEL[t.status]}</span>
                    <span className="t-picks">
                      {t.ref_pick !== null ? `基准纬 ${t.ref_pick}` : "—"}
                      <span className="arrow">→</span>
                      {t.read_seq !== null ? `回读行 ${t.read_seq}` : "无回读"}
                    </span>
                    <span className="t-cells">
                      {t.cells.map((c, j) => (
                        <span
                          key={j}
                          className={
                            "mini-cell"
                            + (c.same ? " same" : "")
                            + (c.ref === null ? " ref-null" : "")
                            + (c.read === null ? " read-null" : "")
                            + (!c.same && c.ref !== null && c.read !== null
                              ? " diff"
                              : "")
                          }
                          title={
                            c.ref === null
                              ? `基准无（重纬回读 ${c.read}）`
                              : c.read === null
                                ? `回读缺失（基准 ${c.ref}）`
                                : `基准 ${c.ref} / 回读 ${c.read}`
                          }
                        >
                          {c.ref === null ? "·" : c.ref}
                          /
                          {c.read === null ? "·" : c.read}
                        </span>
                      ))}
                    </span>
                    {t.mismatch_count > 0 && (
                      <span className="t-count">差 {t.mismatch_count} 孔</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="readback-wrap">
          <h4>设备回读矩阵（采集序）</h4>
          <table className="grid plain readback-grid">
            <tbody>
              {readbackRows.map((row, i) => (
                <tr
                  key={i}
                  id={`read-row-${i + 1}`}
                  className={selectedReadSeq === i + 1 ? "row-highlight" : ""}
                  data-read-seq={i + 1}
                >
                  <th className="rownum">{i + 1}</th>
                  {[...row].map((bit, j) => (
                    <td key={j} className={bit === "1" ? "one" : "zero"}>
                      {bit}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
