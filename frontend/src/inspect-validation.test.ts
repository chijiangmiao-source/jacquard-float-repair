import { describe, expect, it } from "vitest";
import { MAX_INSPECT_BOUND, validateInspectForm } from "./lib/validation";

const form = (boundText: string, readbackText: string) => ({
  boundText,
  readbackText,
});

describe("validateInspectForm", () => {
  it("接受等宽 0/1 且行数在 H±上限内", () => {
    const { errors, value } = validateInspectForm(form("2", "10\n01\n11"), 4, 2);
    expect(errors).toEqual([]);
    expect(value).toEqual({ maxMisses: 2, readback: ["10", "01", "11"] });
  });

  it("容忍末尾单个换行", () => {
    const { errors, value } = validateInspectForm(form("1", "10\n01\n11\n00\n"), 4, 2);
    expect(errors).toEqual([]);
    expect(value?.readback).toHaveLength(4);
  });

  it("拒绝回读含非法字符或问号", () => {
    expect(validateInspectForm(form("2", "12\n01"), 4, 2).errors.join()).toContain(
      "非法字符",
    );
    expect(validateInspectForm(form("2", "1?\n01"), 4, 2).errors.join()).toContain(
      "非法字符",
    );
  });

  it("拒绝宽度不一致与行内不等宽", () => {
    expect(validateInspectForm(form("2", "100\n01"), 4, 2).errors.join()).toContain(
      "宽度",
    );
    expect(validateInspectForm(form("2", "10\n010"), 4, 2).errors.join()).toContain(
      "宽度一致",
    );
  });

  it("拒绝行数超出 H±上限", () => {
    const r1 = validateInspectForm(form("1", "10"), 4, 2); // 2 < 3
    expect(r1.errors.join()).toContain("超出");
    const r2 = validateInspectForm(form("1", "10\n01\n11\n00\n10\n01"), 4, 2); // 6 > 5
    expect(r2.errors.join()).toContain("超出");
    expect(r2.value).toBeNull();
  });

  it("D=0 时行数必须恰为 H", () => {
    expect(validateInspectForm(form("0", "10\n01\n11"), 4, 2).errors.join()).toContain(
      "超出",
    );
    expect(
      validateInspectForm(form("0", "10\n01\n11\n00"), 4, 2).errors,
    ).toEqual([]);
  });

  it("拒绝夹空行、空格与空矩阵", () => {
    expect(validateInspectForm(form("2", "10\n\n01"), 4, 2).errors.join()).toContain(
      "空行",
    );
    expect(validateInspectForm(form("2", "1 0\n01"), 4, 2).errors.join()).toContain(
      "空格",
    );
    expect(validateInspectForm(form("2", ""), 4, 2).value).toBeNull();
  });

  it("上限越界或非数字被拒绝", () => {
    expect(validateInspectForm(form(`${MAX_INSPECT_BOUND + 1}`, "10"), 4, 2).value).toBeNull();
    expect(validateInspectForm(form("-1", "10"), 4, 2).value).toBeNull();
    expect(validateInspectForm(form("a", "10"), 4, 2).value).toBeNull();
  });

  it("边界 20 接受 H±20 行", () => {
    const rows = Array.from({ length: 24 }, () => "10").join("\n");
    expect(validateInspectForm(form("20", rows), 4, 2).errors).toEqual([]);
  });
});
