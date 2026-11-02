import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
test.use({ actionTimeout: 15000 });
async function defaults(request: any, method = "tool.word.defaults") {
  return (
    await (
      await request.post("/api/bridge", { data: { method, params: {} } })
    ).json()
  ).result;
}
async function load(page: any, c: any) {
  await page
    .locator('input[type=file][accept=".json"]')
    .first()
    .setInputFiles({
      name: "审计配置.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(c)),
    });
}

test("category validates bad counts, recovers, exports and retains results across tools", async ({
  page,
}) => {
  await page.goto("/#/tools/category");
  await page.getByLabel("类别数量 1", { exact: true }).fill("2.5");
  await page.getByRole("button", { name: "生成随机数列", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("整数");
  await page
    .getByRole("link", { name: "均数 / 标准差模拟", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("link", { name: "自定义类别数列", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("整数");
  await page.getByLabel("类别数量 1", { exact: true }).fill("2");
  await page.getByLabel("类别数量 2", { exact: true }).fill("0");
  await page.getByRole("button", { name: "生成随机数列", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toHaveValue("1\n1");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("combobox", { name: "复制格式" }).click();
  await page.getByRole("option", { name: "R 向量", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toHaveValue("c(1, 1)");
  const saving = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 CSV", exact: true }).click();
  const csv = readFileSync((await (await saving).path())!, "utf8");
  expect(csv.trim().split(/\r?\n/)).toHaveLength(3);
  await page
    .getByRole("link", { name: "均数 / 标准差模拟", exact: true })
    .click();
  await page.getByRole("link", { name: "自定义类别数列", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toHaveValue("c(1, 1)");
});

test("numeric retains previous data on failure and recovers to a valid constant distribution", async ({
  page,
}) => {
  await page.goto("/#/tools/numeric");
  await page.locator("#target-mean").fill("10");
  await page.locator("#target-sd").fill("0");
  await page.getByLabel("数值下限", { exact: true }).fill("10");
  await page.getByLabel("数值上限", { exact: true }).fill("10");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toBeVisible();
  const before = await page.getByLabel("全部生成数值").inputValue();
  expect(
    before
      .trim()
      .split(/\s+/)
      .map(Number)
      .every((x) => x === 10),
  ).toBe(true);
  await expect(
    page.getByLabel("模拟数据分布预览", { exact: true }),
  ).toContainText("10 ～ 10");
  await page.locator("#target-sd").fill("-1");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("全部生成数值")).toHaveValue(before);
  await page.locator("#target-sd").fill("0");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "生成模拟数据", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByLabel("全部生成数值")).toHaveValue(before);
});

test("Word review recovery clears obsolete error and exports all rows beyond preview cap", async ({
  page,
  request,
}) => {
  const c = await defaults(request);
  c.groups = [{ ...c.groups[0], n: 301 }];
  c.include_basics = false;
  c.indicators = [];
  c.categoricals = [];
  c.typed_fields = [
    {
      table: 1,
      name: "性别",
      group: c.groups[0].name,
      kind: "gender",
      labels: ["男", "女"],
      weights: [50, 50],
      confirmed: false,
      raw: "待核对",
    },
  ];
  await page.goto("/#/tools/word");
  await load(page, c);
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  await page.getByRole("button", { name: /编辑规则：性别/ }).click();
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "导出完整 Excel", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("共 301 行", { exact: false })).toBeVisible();
  expect(await page.locator(".result-table-scroll tbody tr").count()).toBe(200);
  const saving = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出完整 Excel", exact: true })
    .click();
  const file = await (await saving).path();
  const python = process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python");
  const checked = execFileSync(
    python,
    [
      "-c",
      `import sys
from openpyxl import load_workbook
from io import BytesIO
w=load_workbook(BytesIO(open(sys.argv[1],"rb").read()),read_only=True,data_only=True);s=w.worksheets[0];assert s.max_row==302,s.max_row;assert s.max_column>=2;print('301 complete data rows verified');w.close()`,
      file!,
    ],
    { encoding: "utf8" },
  );
  expect(checked).toContain("verified");
});

test("Word loading a config without import options resets settings rather than reusing old flags", async ({
  page,
  request,
}) => {
  const c = await defaults(request);
  c.import_options = {
    sizes: true,
    rates: true,
    prose: true,
    leave_unknown_blank: true,
    decimal_mode: "source",
  };
  await page.goto("/#/tools/word");
  await load(page, c);
  await expect(
    page.getByRole("checkbox", { name: "采用 Word 中的例数", exact: true }),
  ).toBeChecked();
  delete c.import_options;
  await load(page, c);
  await expect(
    page.getByRole("checkbox", { name: "采用 Word 中的例数", exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "采用正文一般资料", exact: true }),
  ).not.toBeChecked();
  await expect(page.getByRole("combobox", { name: "导入小数精度" })).toHaveText(
    "默认整数（0 位）",
  );
});

test("SHAP valid configuration recovers from load and preview errors", async ({
  page,
  request,
}) => {
  const c = await defaults(request, "tool.shap.defaults");
  c.data.n_samples = 40;
  c.explanation.background_max_samples = 5;
  c.plots.dpi = 72;
  for (const [key, s] of Object.entries(c.plots.plots) as [string, any][])
    s.enabled = key === "bar";
  await page.goto("/#/tools/shap");
  await load(page, {
    schema_version: 1,
    data: { features: [] },
    plots: { common: {} },
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await load(page, c);
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("40");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "生成完整分析", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存当前图", exact: true }),
  ).toBeVisible({ timeout: 90000 });
  await page.getByRole("tab", { name: /数据参数/ }).click();
  await page.getByLabel("样本量", { exact: true }).fill("42");
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await page.getByRole("button", { name: "预览当前样式", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("数据或模型参数已经变化");
  await load(page, c);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("button", { name: "生成完整分析", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存当前图", exact: true }),
  ).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("prose configuration can recover from a bad file and reload the same file input", async ({
  page,
  request,
}) => {
  await page.goto("/#/tools/word");
  await page.getByRole("tab", { name: /文字匹配/ }).click();
  const input = page.locator('input[type=file][accept=".json"]').last();
  await input.setInputFiles({
    name: "文字.json",
    mimeType: "application/json",
    buffer: Buffer.from("{}"),
  });
  await expect(page.getByRole("alert")).toBeVisible();
  const r = await request.post("/api/bridge", {
    data: {
      method: "tool.word.prose.parse",
      params: {
        text: "对照组10例，年龄（60±4）岁。试验组12例，年龄（59±3）岁。",
      },
    },
  });
  const doc = (await r.json()).result;
  await input.setInputFiles({
    name: "文字.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(doc)),
  });
  await expect(page.getByLabel("一般资料原文")).toHaveValue(doc.source_text);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(input).toHaveValue("");
});

test("SHAP partial plot configuration remains usable when the selected plot is absent", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const c = await defaults(request, "tool.shap.defaults");
  await page.goto("/#/tools/shap");
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await page.getByRole("button", { name: "单样本力图", exact: true }).click();
  c.plots.plots = { bar: c.plots.plots.bar };
  await load(page, c);
  await expect(page.getByLabel("字体列表", { exact: true })).toBeVisible();
  await expect(page.locator(".style-navigation > button")).toHaveText([
    "公共样式",
    "特征重要性条形图",
  ]);
  expect(errors).toEqual([]);
  await page
    .getByRole("button", { name: "特征重要性条形图", exact: true })
    .click();
  await expect(page.getByLabel("图片文件名", { exact: true })).toHaveValue(
    c.plots.plots.bar.filename,
  );
});
