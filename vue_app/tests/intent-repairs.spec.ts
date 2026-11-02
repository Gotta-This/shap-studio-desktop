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
      name: "参数.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(c)),
    });
}
async function save(page: any) {
  const p = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  return JSON.parse(readFileSync((await (await p).path())!, "utf8"));
}
async function range(page: any) {
  await page.getByRole("combobox", { name: "生成模式" }).click();
  await page.getByRole("option", { name: "按上下限均匀随机生成" }).click();
}

test("range generation ignores cleared hidden targets and reports only applicable values", async ({
  page,
}) => {
  await page.goto("/#/tools/numeric");
  await page.locator("#target-mean").fill("");
  await page.locator("#target-sd").fill("-1");
  await range(page);
  await page.getByLabel("数值下限", { exact: true }).fill("1");
  await page.getByLabel("数值上限", { exact: true }).fill("100");
  await page.locator("#numeric-seed").fill("");
  const started = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/bridge") &&
      r.request().postDataJSON()?.method === "tool.job.start",
  );
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  const id = (await (await started).json()).result.id;
  await expect(page.getByLabel("全部生成数值")).toBeVisible();
  const values = (await page.getByLabel("全部生成数值").inputValue())
    .trim()
    .split(/\s+/)
    .map(Number);
  expect(values).toHaveLength(70);
  expect(values.every((x) => x >= 1 && x <= 100)).toBe(true);
  const state = await page.evaluate(async (id) => {
    const { api } = await import("/src/lib/api.ts");
    return api("tool.job.status", { id });
  }, id);
  expect(state.result.params.seed).toBeNull();
  expect(state.result.params.mean).toBe(0);
  expect(state.result.params.sd).toBe(0);
  await page.getByText("目标与实际（上次生成参数）", { exact: true }).click();
  const table = page.locator("details.tool-note table");
  await expect(
    table.locator("tbody tr").nth(1).locator("td").nth(1),
  ).toHaveText("—");
  await expect(
    table.locator("tbody tr").nth(2).locator("td").nth(3),
  ).toHaveText("—");
  await expect(
    page.getByText("按上下限均匀随机生成，不约束均数和标准差。", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.screenshot({
    path: "test-results/intent-numeric-range.png",
    fullPage: true,
  });
});

test("Word rename and removal preserve other tables including derived fields", async ({
  page,
  request,
}) => {
  const c = await defaults(request);
  c.include_basics = false;
  c.indicators = [];
  c.categoricals = [];
  c.typed_fields = [];
  for (const table of [1, 2])
    for (const g of c.groups)
      c.typed_fields.push(
        {
          table,
          name: "原指标",
          group: g.name,
          kind: "mean_sd",
          mean: 10,
          sd: 1,
          digits: 0,
          confirmed: true,
        },
        {
          table,
          name: "派生结果",
          group: g.name,
          kind: "derived",
          from_field: "原指标",
          positive_labels: ["有效"],
          confirmed: true,
        },
      );
  await page.goto("/#/tools/word");
  await load(page, c);
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  const first = page.locator(".word-fields-table").first();
  await first.getByLabel("输出列名").first().fill("本表新指标");
  let saved = await save(page);
  for (const f of saved.typed_fields) {
    expect(f.kind === "derived" ? f.from_field : f.name).toBe(
      f.table === 1 ? "本表新指标" : "原指标",
    );
  }
  await first
    .getByRole("button", { name: "移除同名指标", exact: true })
    .first()
    .click();
  saved = await save(page);
  expect(saved.typed_fields).toHaveLength(4);
  expect(saved.typed_fields.every((f: any) => f.table === 2)).toBe(true);
  expect(
    saved.typed_fields
      .filter((f: any) => f.kind === "derived")
      .every((f: any) => f.from_field === "原指标"),
  ).toBe(true);
});

test("Word precision switch updates defaults but keeps a manually edited row", async ({
  page,
}) => {
  const python = process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python");
  const file = execFileSync(
    python,
    [
      "-c",
      `from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile
from xml.etree import ElementTree as E
w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}';d=E.Element(w+'document');b=E.SubElement(d,w+'body');t=E.SubElement(b,w+'tbl')
for row in [['项目','对照组(n=10)','中药组(n=12)'],['评分','50.00±5.00','60.00±5.00']]:
 tr=E.SubElement(t,w+'tr')
 for text in row:E.SubElement(E.SubElement(E.SubElement(E.SubElement(tr,w+'tc'),w+'p'),w+'r'),w+'t').text=text
p=Path(mkdtemp())/'精度.docx'
with ZipFile(p,'w') as z:z.writestr('word/document.xml',E.tostring(d))
print(p)`,
    ],
    { encoding: "utf8" },
  ).trim();
  await page.goto("/#/tools/word");
  await page.getByLabel("导入 Word 文档").setInputFiles(file);
  await expect(page.getByRole("tab", { name: /表格匹配/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  const precision = page.getByRole("combobox", { name: "导入小数精度" });
  await precision.click();
  await page.getByRole("option", { name: "沿用原文精度", exact: true }).click();
  await page
    .getByRole("button", { name: "匹配并确认组别", exact: true })
    .click();
  let saved = await save(page);
  expect(
    [...saved.indicators, ...saved.typed_fields].map((f: any) => f.digits),
  ).toEqual([2, 2]);
  await page
    .getByRole("button", { name: /编辑规则：评分/ })
    .first()
    .click();
  await page.getByLabel("小数位（0～4）", { exact: true }).fill("4");
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await precision.click();
  await page
    .getByRole("option", { name: "默认整数（0 位）", exact: true })
    .click();
  await page
    .getByRole("button", { name: "匹配并确认组别", exact: true })
    .click();
  saved = await save(page);
  expect(
    [...saved.indicators, ...saved.typed_fields]
      .map((f: any) => f.digits)
      .sort(),
  ).toEqual([0, 4]);
  await page
    .getByRole("button", { name: "查看原表与识别草稿", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "表格识别草稿", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /50/ })
    .first()
    .click();
  await page.getByLabel("小数位（0～4）", { exact: true }).fill("3");
  const converted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/bridge") &&
      r.request().postDataJSON()?.method === "tool.word.convert",
  );
  await page.getByRole("combobox", { name: "字段数据类型" }).click();
  await page.getByRole("option", { name: "均数±标准差", exact: true }).click();
  await converted;
  await expect(page.locator('[role="listbox"]')).toHaveCount(0);
  await page.screenshot({ path: "test-results/intent-word-nested-editor.png" });
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "编辑字段 · 评分" }),
  ).toHaveCount(0);
  await page.getByRole('dialog', {name:'Word 原表与识别草稿'})
    .getByRole('button', {name:'Close',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await precision.click();
  await page.getByRole("option", { name: "沿用原文精度", exact: true }).click();
  await page
    .getByRole("button", { name: "匹配并确认组别", exact: true })
    .click();
  saved = await save(page);
  expect(
    [...saved.indicators, ...saved.typed_fields]
      .map((f: any) => f.digits)
      .sort(),
  ).toEqual([2, 3]);
});

test("SHAP output directory loads saves and controls actual generated artifacts", async ({
  page,
  request,
}) => {
  const c = await defaults(request, "tool.shap.defaults");
  c.data.n_samples = 20;
  // All writes stay inside the isolated test profile.
  const folder = resolve(".v3-data/browser-tests/intent-output");
  c.plots.output_dir = folder + "/loaded";
  await page.goto("/#/tools/shap");
  await load(page, c);
  await expect(page.getByLabel("分析输出目录", { exact: true })).toHaveValue(
    c.plots.output_dir,
  );
  await page
    .getByLabel("分析输出目录", { exact: true })
    .fill(folder + "/edited");
  const saved = await save(page);
  expect(saved.plots.output_dir).toBe(folder + "/edited");
  await load(page, saved);
  await expect(page.getByLabel("分析输出目录", { exact: true })).toHaveValue(
    folder + "/edited",
  );
  const started = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/bridge") &&
      r.request().postDataJSON()?.method === "tool.job.start",
  );
  await page.getByRole("button", { name: "仅生成数据", exact: true }).click();
  const id = (await (await started).json()).result.id;
  await expect(
    page.getByRole("button", { name: "结果文件夹", exact: true }),
  ).toBeVisible();
  const state = await page.evaluate(async (id) => {
    const { api } = await import("/src/lib/api.ts");
    return api("tool.job.status", { id });
  }, id);
  expect(state.result.folder.startsWith(folder + "/edited/")).toBe(true);
  expect(state.result.config.plots.output_dir).toBe(folder + "/edited");
  expect(
    JSON.parse(
      readFileSync(resolve(state.result.folder, "parameters.json"), "utf8"),
    ).plots.output_dir,
  ).toBe(folder + "/edited");
});
