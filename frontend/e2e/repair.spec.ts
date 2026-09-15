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
