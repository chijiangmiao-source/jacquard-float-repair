import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function fillForm(overrides: Partial<Record<string, string>> = {}) {
  const values = {
    "高度 H": "2",
    "宽度 W": "2",
    "每纬孔数 K": "1",
    "最大循环浮长 L": "2",
    "纹板矩阵": "11\n00",
    ...overrides,
  };
  for (const [label, value] of Object.entries(values)) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
}

const okResponse = {
  ok: true,
  height: 2,
  width: 2,
  picks: 1,
  max_float: 2,
  changes: 2,
  solve_seconds: 0.01,
  matrix: [[1, 0], [0, 1]],
  diff: [
    [
      { input: "1", output: 1, kind: "original_hole", counts_as_change: false },
      { input: "1", output: 0, kind: "removed_hole", counts_as_change: true },
    ],
    [
      { input: "0", output: 0, kind: "kept_blank", counts_as_change: false },
      { input: "0", output: 1, kind: "added_hole", counts_as_change: true },
    ],
  ],
};

describe("录入到结果展示", () => {
  it("提交合法纹板后展示改动总数与原孔/补孔/改孔", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(okResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fillForm();
    fireEvent.click(screen.getByText("修复纹板"));

    await waitFor(() =>
      expect(screen.getByTestId("changes-total")).toHaveTextContent("改动总数：2"),
    );
    expect(screen.getByTestId("changes-added")).toHaveTextContent("补孔 1 处");
    expect(screen.getByTestId("changes-removed")).toHaveTextContent("改孔 1 处");

    const cells = screen.getAllByTitle(/原孔|补孔|改孔|原空/);
    const kinds = cells.map((c) => c.getAttribute("data-kind"));
    expect(kinds).toContain("original_hole");
    expect(kinds).toContain("added_hole");
    expect(kinds).toContain("removed_hole");

    // 请求体形状
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({
      height: 2, width: 2, picks: 1, max_float: 2, rows: ["11", "00"],
    });
  });

  it("非法字符提交被整次拒绝并清除旧解", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ok: false, errors: ["第 1 行含非法字符 2"] }),
          { status: 400 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fillForm();
    fireEvent.click(screen.getByText("修复纹板"));
    await waitFor(() => screen.getByTestId("changes-total"));
    expect(screen.getByTestId("result-grid")).toBeInTheDocument();

    // 第二次提交含非法字符：前端直接拒绝，不调用接口，旧解必须消失。
    fillForm({ "纹板矩阵": "12\n00" });
    fireEvent.click(screen.getByText("修复纹板"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.queryByTestId("result-grid")).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/当前录入存在问题/)).toBeInTheDocument();
  });

  it("服务端 400 拒绝也清除旧解", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ok: false, errors: ["矩阵各行长度不等"] }),
          { status: 400 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fillForm();
    fireEvent.click(screen.getByText("修复纹板"));
    await waitFor(() => screen.getByTestId("changes-total"));

    // 构造一个能过前端校验但服务端拒绝的场景：直接再次点击同样数据，
    // 这里改用 mock 的第二次返回验证清旧解行为。
    fireEvent.click(screen.getByText("修复纹板"));
    await waitFor(() =>
      expect(screen.queryByTestId("changes-total")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("请求被拒绝")).toBeInTheDocument();
  });

  it("不可修复时明确提示且不残留旧纹板", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            infeasible: true,
            errors: ["不存在同时满足每纬抬综数与循环浮长的修复矩阵"],
          }),
          { status: 422 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fillForm();
    fireEvent.click(screen.getByText("修复纹板"));
    await waitFor(() => screen.getByTestId("changes-total"));

    fireEvent.click(screen.getByText("修复纹板"));
    await waitFor(() =>
      expect(screen.queryByTestId("result-grid")).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("不可修复")).toBeInTheDocument();
    expect(
      screen.getByText(/上次结果已清除/),
    ).toBeInTheDocument();
  });
});
