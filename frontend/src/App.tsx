import { useMemo, useState } from "react";
import { repairMatrix, ApiError } from "./lib/api";
import type { RepairResponse } from "./lib/types";
import { validateForm, type RawForm } from "./lib/validation";
import { ResultView } from "./components/ResultView";

const PLACEHOLDER = ["01?1", "1?01", "011?", "10?1"].join("\n");

export default function App() {
  const [form, setForm] = useState<RawForm>({
    heightText: "4",
    widthText: "4",
    picksText: "2",
    maxFloatText: "4",
    rowsText: PLACEHOLDER,
  });
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<RepairResponse | null>(null);
  const [infeasible, setInfeasible] = useState(false);
  const [loading, setLoading] = useState(false);

  const live = useMemo(() => validateForm(form), [form]);

  function update<K extends keyof RawForm>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
    // 重新录入后清除上次提交的拒绝信息（结果本身在再次提交时才处理）。
    setErrors([]);
    setInfeasible(false);
  }

  // 任何重新提交都先清空上次纹板，保证非法 / 不可修复时不残留旧解。
  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResult(null);
    setInfeasible(false);
    setErrors([]);

    const { errors: vErrors, value } = validateForm(form);
    if (vErrors.length > 0 || value === null) {
      // 实时提示区已展示同样信息，这里不重复设置。
      return;
    }
    setLoading(true);
    try {
      const resp = await repairMatrix(value);
      setResult(resp);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors([err.message]);
        setInfeasible(err.infeasible);
      } else {
        setErrors(["请求失败，请重试"]);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <h1>提花纹板循环浮长修复器</h1>
      <p className="subtitle">
        破损纹板会同时丢孔（0→1 补孔）与误孔（1→0 改孔）。求解器在保证
        <b> 每纬恰有 K 个孔 </b>且每列
        <b> 末行与首行相接后连续相同位不超过 L </b>的前提下，最小化总改动数；
        并列时按行优先、0 小于 1 取字典序最小解。
      </p>

      <form className="form" onSubmit={onSubmit} noValidate>
        <div className="params">
          <label>
            高度 H（2–200）
            <input
              aria-label="高度 H"
              inputMode="numeric"
              value={form.heightText}
              onChange={(e) => update("heightText", e.target.value)}
            />
          </label>
          <label>
            宽度 W（2–10）
            <input
              aria-label="宽度 W"
              inputMode="numeric"
              value={form.widthText}
              onChange={(e) => update("widthText", e.target.value)}
            />
          </label>
          <label>
            每纬孔数 K（0–W）
            <input
              aria-label="每纬孔数 K"
              inputMode="numeric"
              value={form.picksText}
              onChange={(e) => update("picksText", e.target.value)}
            />
          </label>
          <label>
            最大循环浮长 L（1–H）
            <input
              aria-label="最大循环浮长 L"
              inputMode="numeric"
              value={form.maxFloatText}
              onChange={(e) => update("maxFloatText", e.target.value)}
            />
          </label>
        </div>

        <label className="rows-label">
          纹板矩阵（每行一个字符串，字符仅为 0、1、?；? 为缺失格，取值不计改动）
          <textarea
            aria-label="纹板矩阵"
            rows={8}
            spellCheck={false}
            value={form.rowsText}
            placeholder={PLACEHOLDER}
            onChange={(e) => update("rowsText", e.target.value)}
          />
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "求解中…" : "修复纹板"}
        </button>
      </form>

      {live.errors.length > 0 && (
        <div className="hint" role="status" aria-label="录入提示">
          <h2>当前录入存在问题（提交将整次拒绝并清除上次结果）</h2>
          <ul>
            {live.errors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {errors.length > 0 && (
        <div
          className={infeasible ? "infeasible" : "errors"}
          role="alert"
          aria-label={infeasible ? "不可修复" : "服务错误"}
        >
          <h2>{infeasible ? "不可修复" : "请求被拒绝"}</h2>
          <ul>
            {errors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
          {infeasible && (
            <p>不存在同时满足每纬孔数 K 与循环浮长 L 的矩阵，上次结果已清除。</p>
          )}
        </div>
      )}

      {result !== null && <ResultView result={result} />}
    </main>
  );
}
