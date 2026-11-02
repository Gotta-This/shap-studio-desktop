import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
test("Word import generates a real Excel with every recognized field", async ({
  page,
}) => {
  const python = process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python");
  const file = execFileSync(
    python,
    [
      "-c",
      `import tempfile,sys
from pathlib import Path
from xml.etree import ElementTree as E
from zipfile import ZipFile
w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}';root=E.Element(w+'document');body=E.SubElement(root,w+'body');t=E.SubElement(body,w+'tbl')
for row in [['项目','对照组(n=10)','中药组(n=12)'],['年龄','58.2±4.1','57.9±3.5']]:
 r=E.SubElement(t,w+'tr')
 for text in row:E.SubElement(E.SubElement(E.SubElement(E.SubElement(r,w+'tc'),w+'p'),w+'r'),w+'t').text=text
p=Path(tempfile.mkdtemp())/'统计表.docx'
with ZipFile(p,'w') as z:z.writestr('word/document.xml',E.tostring(root))
print(p)`,
    ],
    { encoding: "utf8" },
  ).trim();
  await page.goto("/#/tools/word");
  await page.getByLabel("导入 Word 文档").setInputFiles(file);
  await expect(
    page.getByRole("button", { name: "匹配并确认组别" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看原表与识别草稿" }).click();
  await expect(page.getByRole("dialog")).toContainText("表名与原表");
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await expect(
    page.getByRole("button", { name: "生成模拟数据", exact: true }),
  ).toBeEnabled();
  await page.getByRole("tab", { name: /基础资料/ }).click();
  await page.getByRole("button", { name: "匹配并确认组别" }).click();
  await expect(page.getByLabel("当前组生成例数")).toHaveValue("70");
  await page.screenshot({
    path: "test-results/v3-word-basics.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  await expect(
    page.getByRole("columnheader", { name: "Word 原文" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "导出完整 Excel" }),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    page.getByRole("columnheader", { name: "年龄", exact: true }),
  ).toBeVisible();
  const viewport = page.locator(".result-table-scroll");
  await expect(viewport).toBeVisible();
  expect(
    await viewport.evaluate((node: HTMLElement) => node.clientHeight),
  ).toBeLessThanOrEqual(560);
  await page.screenshot({
    path: "test-results/v3-word-export.png",
    fullPage: true,
  });
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出完整 Excel" }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
});
test("SHAP parameter arrays can add features and real data-only generation succeeds", async ({
  page,
}) => {
  await page.goto("/#/tools/shap");
  await expect(page.getByLabel("样本量", { exact: true })).toBeVisible();
  await page.getByLabel("样本量", { exact: true }).fill("40");
  await page.getByRole("button", { name: "添加连续变量", exact: true }).click();
  await expect(
    page.getByLabel("连续变量名称", { exact: true }).last(),
  ).toHaveValue(/新连续变量/);
  await page.getByRole("tab", { name: /模型与分类变量/ }).click();
  await page.getByRole("button", { name: "添加分类变量", exact: true }).click();
  await expect(
    page.getByLabel("分类变量名称", { exact: true }).last(),
  ).toHaveValue(/新分类变量/);
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await page.getByRole("button", { name: "单样本力图", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "预览当前样式", exact: true }),
  ).toBeDisabled();
  await page.getByRole("tab", { name: /结果与导出/ }).click();
  await page.getByRole("button", { name: "仅生成数据", exact: true }).click();
  await expect(page.getByRole("button", { name: "结果文件夹" })).toBeVisible({
    timeout: 60000,
  });
  await expect(
    page.getByRole("columnheader", { name: "患者ID", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/v3-shap-data.png",
    fullPage: true,
  });
});
test("local bridge rejects cross-origin requests", async ({ request }) => {
  const response = await request.post("/api/bridge", {
    headers: { Origin: "https://example.com" },
    data: { method: "state", params: {} },
  });
  expect(response.status()).toBe(403);
});

test("Qt prose workflow generates without a Word file and blocks stale text", async ({
  page,
}) => {
  await page.goto("/#/tools/word");
  await page.getByRole("button", { name: "正文转竖表" }).click();
  await page
    .getByLabel("一般资料原文")
    .fill("对照组10例，年龄（58±4）岁。试验组12例，年龄（57±3）岁。");
  await page
    .getByRole("button", { name: "识别 / 重新识别文字", exact: true })
    .click();
  await expect(page.getByLabel("对照组 文字例数")).toHaveValue("10");
  await expect(page.getByLabel("试验组 文字例数")).toHaveValue("12");
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "导出完整 Excel" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("共 22 行", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: /文字匹配/ }).click();
  await page.getByLabel("一般资料原文").fill("改动后的原文");
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("重新识别");
});

test("SHAP real plots, style inheritance, existing-model preview and full tables", async ({
  page,
  request,
}) => {
  test.setTimeout(120000);
  const response = await request.post("/api/bridge", {
    data: { method: "tool.shap.defaults", params: {} },
  });
  const config = (await response.json()).result;
  config.data.n_samples = 205;
  config.plots.dpi = 72;
  config.explanation.background_max_samples = 10;
  for (const [name, style] of Object.entries(config.plots.plots) as [
    string,
    any,
  ][])
    style.enabled = name === "bar";
  await page.goto("/#/tools/shap");
  await page.locator("input[type=file]").setInputFiles({
    name: "analysis.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(config)),
  });
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("205");
  await page.getByRole("button", { name: "生成完整分析", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存当前图", exact: true }),
  ).toBeVisible({ timeout: 90000 });
  await expect(page.locator("img.result-figure")).toBeVisible();
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await page
    .getByRole("button", { name: "特征重要性条形图", exact: true })
    .click();
  await expect(page.getByLabel("字号", { exact: true })).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "独立设置 字号", exact: true })
    .check();
  await page.getByLabel("字号", { exact: true }).fill("13");
  await page.getByRole("button", { name: "预览当前样式", exact: true }).click();
  await expect(page.locator(".style-preview img")).toBeVisible({
    timeout: 60000,
  });
  await page.screenshot({
    path: "test-results/v3-shap-styles.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: /结果与导出/ }).click();
  await page.getByRole("button", { name: "模拟数据", exact: true }).click();
  await expect(page.getByText("共 205 行", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(page.getByText("第 2 / 2 页", { exact: false })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(5);
  await page.getByRole("button", { name: "模型系数", exact: true }).click();
  await expect(
    page.getByRole("columnheader", { name: "系数", exact: true }),
  ).toBeVisible();
});
