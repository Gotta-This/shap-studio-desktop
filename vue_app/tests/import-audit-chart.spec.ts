import { test, expect } from "@playwright/test";
import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { buildHistogram } from "../src/lib/histogram";

test("histogram bins count all values including max and constant/negative samples", () => {
  for (const values of [
    [-5, -3, -1, 0, 3, 5],
    Array(70).fill(0),
    [0.0001, 0.0002, 0.0003],
  ]) {
    const chart = buildHistogram(values)!;
    expect(chart.bins.reduce((n, bin) => n + bin.count, 0)).toBe(values.length);
    expect(chart.yTicks.every(Number.isInteger)).toBe(true);
    expect(chart.ceiling).toBeGreaterThanOrEqual(
      Math.max(...chart.bins.map((bin) => bin.count)),
    );
    expect(chart.xTicks.every(Number.isFinite)).toBe(true);
  }
  expect(buildHistogram([])).toBeNull();
});

test("numeric plot shows both axes, true range and counts", async ({
  page,
}) => {
  await page.goto("/#/tools/numeric");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  const chart = page.getByLabel("模拟数据分布预览", { exact: true });
  await expect(chart).toBeVisible();
  await expect(chart.getByText("频数（个）", { exact: true })).toBeVisible();
  await expect(chart.getByText("数值区间", { exact: true })).toBeVisible();
  await expect(chart.locator("figcaption")).toContainText("共 70 个数值");
  const values = (await page.getByLabel("全部生成数值").inputValue())
    .trim()
    .split(/\s+/)
    .map(Number);
  await expect(chart.locator("figcaption")).toContainText(
    `${Math.min(...values)} ～ ${Math.max(...values)}`,
  );
  await chart.locator(".hist-bin").first().focus();
  await expect(chart.locator(".distribution-readout")).toContainText("个");
  await page.screenshot({ path: "test-results/numeric-axis-chart.png" });
});

test("toast dismisses after two seconds and a newer notification resets its timer", async ({
  page,
}) => {
  await page.goto("/#/tools/numeric");
  await expect(page.locator(".page-heading")).toBeVisible();
  await page.clock.install({ time: new Date("2026-11-02T00:00:00Z") });
  await page.clock.pauseAt(new Date("2026-11-02T00:00:01Z"));
  await page.evaluate(async () => {
    const api = await import("/src/lib/api.ts");
    api.notify("第一条提示");
  });
  await page.clock.fastForward(1500);
  await expect(page.locator(".toast")).toContainText("第一条提示");
  await page.evaluate(async () => {
    const api = await import("/src/lib/api.ts");
    api.notify("第二条提示");
  });
  await page.clock.fastForward(1999);
  await expect(page.locator(".toast")).toContainText("第二条提示");
  await page.clock.fastForward(1);
  await expect(page.locator(".toast")).toHaveCount(0);
});

const corpus = resolve("../word");
const folder = existsSync(corpus)
  ? readdirSync(corpus).find((name) => name.startsWith("6.03修回-杨见萍"))
  : undefined;
const source = folder
  ? resolve(
      corpus,
      folder,
      readdirSync(resolve(corpus, folder)).find((name) =>
        name.endsWith(".docx"),
      ) || "missing",
    )
  : "";
test("real Word import automatically matches, audits and highlights every pending rule", async ({
  page,
}) => {
  test.skip(!source || !existsSync(source), "Local manuscript fixture");
  await page.goto("/#/tools/word");
  await page.getByLabel("导入 Word 文档").setInputFiles(source);
  await expect(page.getByRole("tab", { name: /表格匹配/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.locator(".rule-audit")).toContainText("已自动核对");
  await expect(page.locator(".rule-audit")).toContainText("待人工确认");
  const row = page.locator(".word-fields-table tr.rule-pending").first();
  await expect(row).toBeVisible();
  expect(
    await row
      .locator("td")
      .first()
      .evaluate((node) => getComputedStyle(node).backgroundColor),
  ).toBe("rgb(255, 241, 242)");
  await page.screenshot({ path: "test-results/word-auto-audit.png" });
  await page.getByRole("button", { name: "定位待确认", exact: true }).click();
  await expect(row).toBeInViewport();
  await page.screenshot({ path: "test-results/word-pending-rows.png" });
});

test("confirming a valid pending rule automatically removes its red highlight", async ({
  page,
  request,
}) => {
  const response = await request.post("/api/bridge", {
    data: { method: "tool.word.defaults" },
  });
  const config = (await response.json()).result;
  config.groups = [config.groups[0]];
  config.include_basics = false;
  config.typed_fields = [
    {
      table: 1,
      name: "确认状态检查",
      group: config.groups[0].name,
      kind: "gender",
      labels: ["男", "女"],
      weights: [50, 50],
      confirmed: false,
    },
  ];
  await page.goto("/#/tools/word");
  await page
    .locator('input[type=file][accept=".json"]')
    .setInputFiles({
      name: "待确认.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  const row = page.locator(".word-fields-table tbody tr").first();
  await expect(row).toHaveClass(/rule-pending/);
  await row.getByRole("button", { name: /编辑规则/ }).click();
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(row).not.toHaveClass(/rule-pending/);
  await expect(page.locator(".rule-audit")).toContainText("参数核对通过");
});
