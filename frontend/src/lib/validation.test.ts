import { describe, expect, it } from "vitest";
import { validateForm } from "./validation";

const valid = {
  heightText: "3",
  widthText: "2",
  picksText: "1",
  maxFloatText: "3",
  rowsText: "01\n10\n01",
};

describe("validateForm", () => {
  it("接受合法输入", () => {
    const { errors, value } = validateForm(valid);
    expect(errors).toEqual([]);
    expect(value).toEqual({
      height: 3,
      width: 2,
      picks: 1,
      maxFloat: 3,
      rows: ["01", "10", "01"],
    });
  });

  it("容忍 textarea 末尾单个换行，仍视为合法", () => {
    const { errors, value } = validateForm({ ...valid, rowsText: "01\n10\n01\n" });
    expect(errors).toEqual([]);
    expect(value?.rows).toEqual(["01", "10", "01"]);
  });

  it.each([
    ["非法字符", { ...valid, rowsText: "02\n10\n01" }],
    ["非等长行", { ...valid, rowsText: "0\n10\n01" }],
    ["行宽与W不符", { ...valid, rowsText: "010\n101\n011" }],
    ["行数与H不符", { ...valid, heightText: "2" }],
    ["高度越界小", { ...valid, heightText: "1" }],
    ["高度越界大", { ...valid, heightText: "201" }],
    ["宽度越界", { ...valid, widthText: "11" }],
    ["K越界", { ...valid, picksText: "3" }],
    ["K为负", { ...valid, picksText: "-1" }],
    ["L越界", { ...valid, maxFloatText: "4" }],
    ["L为0", { ...valid, maxFloatText: "0" }],
    ["非数字", { ...valid, heightText: "abc" }],
    ["空矩阵", { ...valid, rowsText: "" }],
    ["夹空行", { ...valid, rowsText: "01\n\n10" }],
    ["前导空行", { ...valid, heightText: "4", rowsText: "\n01\n10\n01" }],
    ["行内空格", { ...valid, rowsText: "0 1\n10\n01" }],
    ["行尾空格", { ...valid, rowsText: "01 \n10\n01" }],
    ["制表符", { ...valid, rowsText: "01\n\t10\n01" }],
    ["全角空格", { ...valid, rowsText: "01\n1　0\n01" }],
  ])("拒绝：%s", (_name, form) => {
    const { errors, value } = validateForm(form);
    expect(errors.length).toBeGreaterThan(0);
    expect(value).toBeNull();
  });

  it("接受边界值 H=200 W=10 K=0/10 L=1/H", () => {
    const rows = Array(200).fill("?".repeat(10)).join("\n");
    expect(
      validateForm({ ...valid, heightText: "200", widthText: "10",
        picksText: "0", maxFloatText: "1", rowsText: rows }).errors,
    ).toEqual([]);
    expect(
      validateForm({ ...valid, heightText: "200", widthText: "10",
        picksText: "10", maxFloatText: "200", rowsText: rows }).errors,
    ).toEqual([]);
  });
});
