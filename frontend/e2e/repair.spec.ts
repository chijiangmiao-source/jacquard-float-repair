import { expect, test } from "@playwright/test";

async function fillAll(
  page: import("@playwright/test").Page,
  v: { H: string; W: string; K: string; L: string; rows: string },
) {
  await page.getByLabel("高度 H").fill(v.H);
  await page.getByLabel("宽度 W").fill(v.W);
  await page.getByLabel("每纬孔数 K").fill(v.K);
  await page.getByLabel("最大循环浮长 L").fill(v.L);
  await page.getByLabel("纹板矩阵").fill(v.rows);
}

async function submit(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "修复纹板" }).click();
}

test("录入合法纹板到结果展示，并可逐格复算约束", async ({ page }) => {
  await page.goto("/");
  // H=4 W=2 K=1 L=3：原纹板 10/10/01/10 可行（跨首尾游程恰为 3），0 改动。
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "10\n10\n01\n10",
  });
  await submit(page);

  await expect(page.getByTestId("changes-total")).toContainText("改动总数：0");
  await expect(page.getByTestId("result-grid")).toBeVisible();

  // 逐格读取修复矩阵并复算：每行恰 1 个 1，每列环上最长连等 ≤ 3。
  const matrix = await page
    .getByTestId("result-grid")
    .locator("tbody tr")
    .evaluateAll((trs) =>
      trs.map((tr) =>
        [...tr.querySelectorAll("td.cell")].map(
          (td) => Number((td as HTMLElement).dataset.output),
        ),
      ),
    );

  expect(matrix).toHaveLength(4);
  for (const row of matrix) {
    expect(row.reduce((a, b) => a + b, 0)).toBe(1);
  }
  const H = matrix.length;
  for (let j = 0; j < 2; j++) {
    const col = matrix.map((r) => r[j]);
    let run = 1;
    let best = 1;
    for (let t = 1; t <= H; t++) {
      if (col[t % H] === col[(t - 1) % H]) {
        run++;
        best = Math.max(best, run);
      } else {
        run = 1;
      }
    }
    // 全相等列环上只有 H 个格
    if (col.every((v) => v === col[0])) best = H;
    expect(best).toBeLessThanOrEqual(3);
  }

  // 原孔格存在
  await expect(page.locator("td.kind-original_hole").first()).toBeVisible();
});

test("非法字符整次拒绝并清除上次结果", async ({ page }) => {
  await page.goto("/");
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "10\n10\n01\n10",
  });
  await submit(page);
  await expect(page.getByTestId("changes-total")).toContainText("改动总数：0");

  // 改为含非法字符的矩阵再提交
  await page.getByLabel("纹板矩阵").fill("12\n10\n01\n10");
  await submit(page);

  await expect(page.getByText(/当前录入存在问题/)).toBeVisible();
  await expect(page.getByText(/非法字符/)).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
  await expect(page.getByTestId("changes-total")).toHaveCount(0);
});

test("非等长行整次拒绝且不残留旧解", async ({ page }) => {
  await page.goto("/");
  await fillAll(page, {
    H: "3", W: "3", K: "1", L: "3", rows: "100\n01\n100",
  });
  await submit(page);
  await expect(page.getByText(/当前录入存在问题/)).toBeVisible();
  await expect(page.getByText(/长度/)).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
});

test("夹空行或空格整次拒绝，且不得自动删行后继续求解", async ({ page }) => {
  await page.goto("/");
  // 先求出一个合法结果
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "10\n10\n01\n10",
  });
  await submit(page);
  await expect(page.getByTestId("result-grid")).toBeVisible();

  // 在矩阵中间插入空行（高度仍填 4，行数变成 5，且确实夹了空行）
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "10\n10\n\n01\n10",
  });
  await submit(page);
  await expect(page.getByText(/是空行/)).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
  await expect(page.getByTestId("changes-total")).toHaveCount(0);

  // 改为夹空格：同样必须拒绝，不能 trim 后照解
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "1 0\n10\n01\n10",
  });
  await submit(page);
  await expect(page.getByText(/空格/)).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
});

test("越界参数被拒绝", async ({ page }) => {
  await page.goto("/");
  await fillAll(page, {
    H: "3", W: "2", K: "5", L: "3", rows: "10\n01\n10",
  }); // K > W
  await submit(page);
  await expect(page.getByText(/每纬抬综数 K/)).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
});

test("不可修复时明确提示且不残留上次纹板", async ({ page }) => {
  await page.goto("/");
  // 先求一个有解的
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "3", rows: "10\n10\n01\n10",
  });
  await submit(page);
  await expect(page.getByTestId("result-grid")).toBeVisible();

  // 奇环 L=1：无解
  await fillAll(page, {
    H: "3", W: "2", K: "1", L: "1", rows: "??\n??\n??",
  });
  await submit(page);

  await expect(page.getByLabel("不可修复")).toBeVisible();
  await expect(page.getByText("不存在同时满足每纬抬综数与循环浮长的修复矩阵")).toBeVisible();
  await expect(page.getByTestId("result-grid")).toHaveCount(0);
});

test("仅跨首尾才超限的候选被排除（L=2 被迫改动，L=3 零改动）", async ({ page }) => {
  await page.goto("/");
  await fillAll(page, {
    H: "4", W: "2", K: "1", L: "2", rows: "10\n10\n01\n10",
  });
  await submit(page);
  // 0 改动候选因接缝超限被排除，最优为 2 改动
  await expect(page.getByTestId("changes-total")).toContainText("改动总数：2");
  await expect(page.locator("td.kind-added_hole, td.kind-removed_hole")).toHaveCount(2);
});

// ---- 试打核验 ------------------------------------------------------------

async function repairDistinctMatrix(page: import("@playwright/test").Page) {
  // H=4 W=3 K=1 L=3：100/010/001/100 本身可行（环上最长连等为 2），0 改动，
  // 四纬互不相同的程度足以唯一区分正/反向与起点。
  await page.goto("/");
  await fillAll(page, {
    H: "4", W: "3", K: "1", L: "3", rows: "100\n010\n001\n100",
  });
  await submit(page);
  await expect(page.getByTestId("changes-total")).toContainText("改动总数：0");
  await expect(page.getByLabel("试打核验")).toBeVisible();
}

test("核验成功：孔位不符可点选，同时定位修复矩阵基准行与回读行", async ({ page }) => {
  await repairDistinctMatrix(page);

  // 第 2 纬 010 回读成 000（1 孔不符），其余一致；正向、起点 1。
  await page.getByLabel("设备回读矩阵").fill("100\n000\n001\n100");
  await page.getByRole("button", { name: "发起试打核验" }).click();

  await expect(page.getByTestId("inspect-result")).toBeVisible();
  await expect(page.getByTestId("inspect-direction")).toContainText("正向");
  await expect(page.getByTestId("inspect-start")).toContainText("起始纬号：1");
  await expect(page.getByTestId("inspect-score")).toContainText("总分：1");
  await expect(page.getByTestId("inspect-mismatch")).toContainText("1 纬 / 1 孔");

  const timeline = page.getByTestId("inspect-timeline");
  await expect(timeline.locator("[data-status='hole_mismatch']")).toHaveCount(1);
  await expect(timeline.locator("[data-status='match']")).toHaveCount(3);

  // 点选异常纬（时间线第 1 条 = 基准纬 1 / 回读行 1）
  await page.getByTestId("timeline-0").click();
  await expect(page.locator("tr[data-ref-pick='1'].row-highlight")).toHaveCount(1);
  await expect(
    page.locator(".readback-grid tr[data-read-seq='1'].row-highlight"),
  ).toHaveCount(1);
  // 其他行未高亮
  await expect(page.locator("tr[data-ref-pick='2'].row-highlight")).toHaveCount(0);

  // 点选匹配纬（基准纬 2 / 回读行 2），高亮切换
  await page.getByTestId("timeline-1").click();
  await expect(page.locator("tr[data-ref-pick='1'].row-highlight")).toHaveCount(0);
  await expect(page.locator("tr[data-ref-pick='2'].row-highlight")).toHaveCount(1);
  await expect(
    page.locator(".readback-grid tr[data-read-seq='2'].row-highlight"),
  ).toHaveCount(1);
});

test("核验识别反向跨首尾对齐（从第 1 纬反向采集）", async ({ page }) => {
  await repairDistinctMatrix(page);

  // 从第 1 纬反向、跨首尾采集：pick1=100, pick4=100, pick3=001, pick2=010。
  await page.getByLabel("设备回读矩阵").fill("100\n100\n001\n010");
  await page.getByRole("button", { name: "发起试打核验" }).click();

  await expect(page.getByTestId("inspect-result")).toBeVisible();
  await expect(page.getByTestId("inspect-direction")).toContainText("反向");
  await expect(page.getByTestId("inspect-start")).toContainText("起始纬号：1");
  await expect(page.getByTestId("inspect-score")).toContainText("总分：0");
  await expect(page.getByText(/核验通过：全部逐纬匹配/)).toBeVisible();
  await expect(
    page.getByTestId("inspect-timeline").locator("[data-status='match']"),
  ).toHaveCount(4);
});

test("核验输入非法或行数超界：仅清本次核验，修复结果保留", async ({ page }) => {
  await repairDistinctMatrix(page);

  // 1) 非法字符：前端整次拒绝，不出现核验结果，但修复差异视图仍在。
  await page.getByLabel("设备回读矩阵").fill("102\n010\n001\n100");
  await page.getByRole("button", { name: "发起试打核验" }).click();
  await expect(page.getByLabel("核验录入提示")).toBeVisible();
  await expect(page.getByText(/非法字符/)).toBeVisible();
  await expect(page.getByTestId("inspect-result")).toHaveCount(0);
  await expect(page.getByTestId("result-grid")).toBeVisible();
  await expect(page.getByTestId("changes-total")).toContainText("改动总数：0");

  // 2) 行数超出 H±上限：上限取 1（允许 3～5 行），粘贴 6 行。
  await page.getByLabel("送料错纬上限").fill("1");
  await page
    .getByLabel("设备回读矩阵")
    .fill("100\n010\n001\n100\n100\n010");
  await page.getByRole("button", { name: "发起试打核验" }).click();
  await expect(page.getByText(/超出/)).toBeVisible();
  await expect(page.getByTestId("inspect-result")).toHaveCount(0);
  // 修复结果与原差异视图完整保留
  await expect(page.getByTestId("result-grid")).toBeVisible();
  await expect(page.getByTestId("changes-total")).toContainText("改动总数：0");
  await expect(page.locator("td.kind-original_hole").first()).toBeVisible();

  // 3) 改回合法回读仍可正常核验（证明没有污染已批准纹板）。
  await page.getByLabel("送料错纬上限").fill("2");
  await page.getByLabel("设备回读矩阵").fill("100\n010\n001\n100");
  await page.getByRole("button", { name: "发起试打核验" }).click();
  await expect(page.getByTestId("inspect-result")).toBeVisible();
  await expect(page.getByText(/核验通过/)).toBeVisible();
});
