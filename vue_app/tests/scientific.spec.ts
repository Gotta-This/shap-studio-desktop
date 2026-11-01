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
  await page.getByLabel("导入 DOCX 汇总表").setInputFiles(file);
  await expect(
    page.getByRole("heading", { name: "核对基本资料与指标" }),
  ).toBeVisible();
  await expect(
    page.getByText("识别字段", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "导出完整 Excel" }),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    page.getByRole("columnheader", { name: "年龄", exact: true }),
  ).toBeVisible();
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
  const add = page
    .locator("details")
    .filter({ has: page.locator("summary").filter({ hasText: /^输入特征/ }) })
    .first()
    .getByRole("button", { name: "添加一项", exact: true })
    .last();
  await add.click();
  await expect(page.getByLabel("名称", { exact: true }).last()).toHaveValue(
    /新项目/,
  );
  await page.getByRole("button", { name: /生成与导出/ }).click();
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
