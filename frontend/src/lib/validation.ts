// 前端即时校验，规则与后端 app/validation.py 保持一致：
// 高度 2～200、宽度 2～10、K 0～宽度、L 1～高度、行等长且字符仅 0、1、?。

export const MIN_H = 2;
export const MAX_H = 200;
export const MIN_W = 2;
export const MAX_W = 10;
const ALLOWED = new Set(["0", "1", "?"]);

export interface RawForm {
  heightText: string;
  widthText: string;
  picksText: string;
  maxFloatText: string;
  rowsText: string;
}

export interface ValidatedForm {
  height: number;
  width: number;
  picks: number;
  maxFloat: number;
  rows: string[];
}

function parseCount(text: string): number | null {
  const t = text.trim();
  if (!/^\d+$/.test(t)) return null;
  return Number(t);
}

export function validateForm(form: RawForm): {
  errors: string[];
  value: ValidatedForm | null;
} {
  const errors: string[] = [];
  const height = parseCount(form.heightText);
  const width = parseCount(form.widthText);
  const picks = parseCount(form.picksText);
  const maxFloat = parseCount(form.maxFloatText);

  if (height === null || height < MIN_H || height > MAX_H) {
    errors.push(`高度必须是 ${MIN_H}～${MAX_H} 的整数`);
  }
  if (width === null || width < MIN_W || width > MAX_W) {
    errors.push(`宽度必须是 ${MIN_W}～${MAX_W} 的整数`);
  }

  // 不做 trim、不过滤空行：空行与空格都是非法输入，必须整次拒绝。
  // 仅容忍 textarea 末尾因回车产生的唯一一个尾随空串。
  const rawLines = form.rowsText.split("\n");
  if (rawLines.length > 1 && rawLines[rawLines.length - 1] === "") {
    rawLines.pop();
  }
  const rows = rawLines;
  if (rows.length === 0 || rows.every((l) => l === "")) {
    errors.push("矩阵不能为空，每行输入一个由 0、1、? 组成的字符串");
  }
  rows.forEach((row, idx) => {
    if (row === "") {
      errors.push(`第 ${idx + 1} 行是空行（不允许夹空行）`);
      return;
    }
    if (/[ \t　]/.test(row)) {
      errors.push(`第 ${idx + 1} 行含空格（不允许夹空格）`);
      return;
    }
    const bad = [...row].filter((c) => !ALLOWED.has(c));
    if (bad.length > 0) {
      errors.push(
        `第 ${idx + 1} 行含非法字符 ${[...new Set(bad)].join("")}（仅允许 0、1、?）`,
      );
    }
  });

  if (height !== null && rows.length > 0 && rows.length !== height) {
    errors.push(`矩阵行数 ${rows.length} 与高度 ${height} 不一致`);
  }

  const structurallyValid = rows.filter(
    (r) => r !== "" && !/[ \t　]/.test(r) && [...r].every((c) => ALLOWED.has(c)),
  );
  if (width !== null && structurallyValid.length > 0) {
    const lengths = new Set(structurallyValid.map((r) => r.length));
    if (structurallyValid.length === rows.length && lengths.size > 1) {
      errors.push("矩阵各行长度不等（必须为等长矩阵）");
    } else if (
      structurallyValid.length === rows.length &&
      [...lengths][0] !== width
    ) {
      errors.push(`行宽 ${[...lengths][0]} 与宽度 ${width} 不一致`);
    }
  }

  const w = width ?? MAX_W;
  if (picks === null || picks < 0 || picks > w) {
    errors.push(`每纬抬综数 K 必须是 0～${width ?? MAX_W} 的整数`);
  }
  const h = height ?? MAX_H;
  if (maxFloat === null || maxFloat < 1 || maxFloat > h) {
    errors.push(`最大循环浮长 L 必须是 1～${height ?? MAX_H} 的整数`);
  }

  if (errors.length > 0 || height === null || width === null ||
      picks === null || maxFloat === null) {
    return { errors, value: null };
  }
  return {
    errors,
    value: { height, width, picks, maxFloat, rows },
  };
}
