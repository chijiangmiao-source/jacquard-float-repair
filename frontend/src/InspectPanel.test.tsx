import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function fillRepairForm() {
  const values: Record<string, string> = {
    "高度 H": "2",
    "宽度 W": "2",
    "每纬孔数 K": "1",
    "最大循环浮长 L": "2",
    "纹板矩阵": "11\n00",
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

function inspectResponse(over: Record<string, unknown> = {}) {
  return {
    ok: true,
    height: 2,
    width: 2,
    readback_rows: 2,
    max_misses: 2,
    direction: "forward",
    start_pick: 1,
    score: 1,
    event_count: 0,
    miss_count: 0,
    repeat_count: 0,
    mismatch_picks: 1,
    mismatch_cells: 1,
    mapping: [[1], [2]],
    events: [],
    timeline: [
      {
        kind: "aligned",
        status: "hole_mismatch",
        ref_pick: 1,
        read_seq: 1,
        ref_row: [1, 0],
        read_row: [1, 1],
        cells: [
          { ref: 1, read: 1, same: true },
          { ref: 0, read: 1, same: false },
        ],
        mismatch_count: 1,
      },
      {
        kind: "aligned",
        status: "match",
        ref_pick: 2,
        read_seq: 2,
        ref_row: [0, 1],
        read_row: [0, 1],
        cells: [
          { ref: 0, read: 0, same: true },
          { ref: 1, read: 1, same: true },
        ],
        mismatch_count: 0,
      },
    ],
    ...over,
  };
}

async function repairThen(fetchMock: ReturnType<typeof vi.fn>) {
  render(<App />);
  fillRepairForm();
  fireEvent.click(screen.getByText("修复纹板"));
  await waitFor(() => screen.getByTestId("changes-total"));
  // 核验面板出现在同一结果页
  expect(screen.getByLabelText("试打核验")).toBeInTheDocument();
  return fetchMock;
}

describe("试打核验", () => {
  it("核验成功展示方向/起点/总分，点选异常纬同时高亮修复矩阵基准行与回读行", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(inspectResponse()), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await repairThen(fetchMock);

    // 回读矩阵默认预填修复矩阵；改为首纬 1 孔不符的回读
    fireEvent.change(screen.getByLabelText("设备回读矩阵"), {
      target: { value: "11\n01" },
    });
    fireEvent.click(screen.getByText("发起试打核验"));

    await waitFor(() => screen.getByTestId("inspect-result"));
    expect(screen.getByTestId("inspect-direction")).toHaveTextContent("正向");
    expect(screen.getByTestId("inspect-start")).toHaveTextContent("起始纬号：1");
    expect(screen.getByTestId("inspect-score")).toHaveTextContent("总分：1");
    expect(screen.getByTestId("inspect-mismatch")).toHaveTextContent("1 纬 / 1 孔");

    const timeline = screen.getByTestId("inspect-timeline");
    expect(timeline.querySelectorAll("[data-status='match']")).toHaveLength(1);
    expect(timeline.querySelectorAll("[data-status='hole_mismatch']")).toHaveLength(1);

    // 点选异常纬（时间线第 1 条）
    fireEvent.click(screen.getByTestId("timeline-0"));

    const refRow = document.querySelector("tr[data-ref-pick='1']");
    const readRow = document.querySelector(".readback-grid tr[data-read-seq='1']");
    expect(refRow?.classList.contains("row-highlight")).toBe(true);
    expect(readRow?.classList.contains("row-highlight")).toBe(true);
    // 未点选的第 2 行不高亮
    const refRow2 = document.querySelector("tr[data-ref-pick='2']");
    expect(refRow2?.classList.contains("row-highlight")).toBe(false);

    // 再点匹配纬，高亮切换
    fireEvent.click(screen.getByTestId("timeline-1"));
    expect(document.querySelector("tr[data-ref-pick='1']")?.classList.contains("row-highlight")).toBe(false);
    expect(document.querySelector("tr[data-ref-pick='2']")?.classList.contains("row-highlight")).toBe(true);

    // 请求体：以修复矩阵为基准
    const [, init] = fetchMock.mock.calls[1];
    expect(JSON.parse(init.body)).toEqual({
      matrix: ["10", "01"],
      readback: ["11", "01"],
      max_misses: 2,
    });
  });

  it("识别反向跨首尾对齐", async () => {
    const reverseBody = inspectResponse({
      direction: "reverse",
      start_pick: 1,
      score: 0,
      mismatch_picks: 0,
      mismatch_cells: 0,
      readback_rows: 2,
      // 从第 1 纬反向采集（跨首尾）：10,01
      timeline: [
        {
          kind: "aligned",
          status: "match",
          ref_pick: 1,
          read_seq: 1,
          ref_row: [1, 0],
          read_row: [1, 0],
          cells: [
            { ref: 1, read: 1, same: true },
            { ref: 0, read: 0, same: true },
          ],
          mismatch_count: 0,
        },
        {
          kind: "aligned",
          status: "match",
          ref_pick: 2,
          read_seq: 2,
          ref_row: [0, 1],
          read_row: [0, 1],
          cells: [
            { ref: 0, read: 0, same: true },
            { ref: 1, read: 1, same: true },
          ],
          mismatch_count: 0,
        },
      ],
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(reverseBody), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await repairThen(fetchMock);
    fireEvent.change(screen.getByLabelText("设备回读矩阵"), {
      target: { value: "10\n01" },
    });
    fireEvent.click(screen.getByText("发起试打核验"));

    await waitFor(() => screen.getByTestId("inspect-result"));
    expect(screen.getByTestId("inspect-direction")).toHaveTextContent("反向");
    expect(screen.getByTestId("inspect-start")).toHaveTextContent("起始纬号：1");
    expect(screen.getByTestId("inspect-score")).toHaveTextContent("总分：0");
    expect(screen.getByText(/核验通过/)).toBeInTheDocument();
  });

  it("前端拦截非法回读：仅清本次核验，修复结果保留", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await repairThen(fetchMock);

    // 含非法字符：前端直接拒绝，不调用 /api/inspect
    fireEvent.change(screen.getByLabelText("设备回读矩阵"), {
      target: { value: "12\n01" },
    });
    fireEvent.click(screen.getByText("发起试打核验"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("inspect-result")).not.toBeInTheDocument();
    // 修复结果与差异视图仍在
    expect(screen.getByTestId("result-grid")).toBeInTheDocument();
    expect(screen.getByTestId("changes-total")).toHaveTextContent("改动总数：2");
    expect(screen.getByLabelText("核验录入提示")).toBeInTheDocument();
  });

  it("服务端 400 拒绝核验：仅清本次核验，修复结果保留", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ok: false, errors: ["回读行数 8 超出 H±2 允许范围"] }),
          { status: 400 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await repairThen(fetchMock);
    // 前端放行（2 行等宽），服务端按更严格理由拒绝
    fireEvent.change(screen.getByLabelText("设备回读矩阵"), {
      target: { value: "10\n01" },
    });
    fireEvent.click(screen.getByText("发起试打核验"));

    await waitFor(() => expect(screen.getByLabelText("核验失败")).toBeInTheDocument());
    expect(screen.getByText(/修复结果仍保留/)).toBeInTheDocument();
    expect(screen.queryByTestId("inspect-result")).not.toBeInTheDocument();
    // 修复结果仍在，未重新求解
    expect(screen.getByTestId("result-grid")).toBeInTheDocument();
    expect(screen.getByTestId("changes-total")).toHaveTextContent("改动总数：2");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("漏纬/重纬时间线可点选定位且错纬计数正确", async () => {
    const body = inspectResponse({
      score: 2,
      event_count: 1,
      miss_count: 1,
      mismatch_picks: 0,
      mismatch_cells: 0,
      readback_rows: 1,
      mapping: [[], [1]],
      timeline: [
        {
          kind: "missing_pick",
          status: "missing_pick",
          ref_pick: 1,
          read_seq: null,
          ref_row: [1, 0],
          read_row: null,
          cells: [
            { ref: 1, read: null, same: false },
            { ref: 0, read: null, same: false },
          ],
          mismatch_count: 0,
        },
        {
          kind: "aligned",
          status: "match",
          ref_pick: 2,
          read_seq: 1,
          ref_row: [0, 1],
          read_row: [0, 1],
          cells: [
            { ref: 0, read: 0, same: true },
            { ref: 1, read: 1, same: true },
          ],
          mismatch_count: 0,
        },
      ],
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(okResponse), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await repairThen(fetchMock);
    fireEvent.change(screen.getByLabelText("设备回读矩阵"), {
      target: { value: "01" },
    });
    fireEvent.click(screen.getByText("发起试打核验"));
    await waitFor(() => screen.getByTestId("inspect-result"));

    expect(screen.getByTestId("inspect-events")).toHaveTextContent("漏纬 1 / 重纬 0");
    expect(screen.getByTestId("inspect-score")).toHaveTextContent("总分：2");
    const missItem = screen.getByTestId("timeline-0");
    expect(missItem.getAttribute("data-status")).toBe("missing_pick");
    fireEvent.click(missItem);
    expect(document.querySelector("tr[data-ref-pick='1']")?.classList.contains("row-highlight")).toBe(true);
    // 漏纬没有回读行，不应有任何回读行高亮
    expect(document.querySelector(".readback-grid tr.row-highlight")).toBeNull();
  });
});
