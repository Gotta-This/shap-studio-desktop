import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
async function defaults(request: any, method = "tool.word.defaults") {
  const response = await request.post("/api/bridge", {
    data: { method, params: {} },
  });
  return (await response.json()).result;
}
async function loadConfig(page: any, value: any) {
  await page.locator('input[type=file][accept=".json"]').setInputFiles({
    name: "参数.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(value)),
  });
}

test("field editor preserves peer parameters, confirmation, column order and derived references", async ({
  page,
  request,
}) => {
  const c = await defaults(request);
  c.include_basics = false;
  c.typed_fields = [];
  for (const g of c.groups) {
    g.n = 10;
    c.typed_fields.push(
      {
        table: 1,
        name: "评分",
        group: g.name,
        kind: "mean_sd",
        mean: g.name === "对照组" ? 50 : 60,
        sd: 5,
        digits: 0,
        confirmed: true,
      },
      {
        table: 1,
        name: "另一指标",
        group: g.name,
        kind: "mean_sd",
        mean: 20,
        sd: 2,
        digits: 0,
        confirmed: true,
      },
    );
  }
  await page.goto("/#/tools/word");
  await loadConfig(page, c);
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  await page.getByRole("button", { name: /50 ± 5/ }).click();
  await page.getByLabel("字段均数", { exact: true }).fill("51");
  await page.getByLabel("字段标准差", { exact: true }).fill("");
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("请补全有效的数值参数");
  await page.getByLabel("字段标准差", { exact: true }).fill("5");
  await page.getByRole("button", { name: "确认并应用", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  const saved = JSON.parse(
    readFileSync((await (await download).path())!, "utf8"),
  );
  const peer = saved.typed_fields.find(
    (f: any) => f.name === "评分" && f.group === "中药组",
  );
  expect(peer.mean).toBe(60);
  expect(peer.confirmed).toBe(true);
  expect(saved.typed_fields[0].name).toBe("评分");
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "导出完整 Excel" }),
  ).toBeVisible({ timeout: 30000 });
});

test("saved prose study selection, raw text and stale status survive reload", async ({
  page,
  request,
}) => {
  const c = await defaults(request);
  const parse = await request.post("/api/bridge", {
    data: {
      method: "tool.word.prose.parse",
      params: {
        text: "对照组10例，年龄（50±5）岁。中药组12例，年龄（55±5）岁。",
      },
    },
  });
  const doc = (await parse.json()).result,
    second = JSON.parse(JSON.stringify(doc.studies[0]));
  second.groups.forEach((g: any) => (g.n = 20));
  second.title = "第二项研究";
  doc.studies.push(second);
  c.prose_document = doc;
  c.study_index = 1;
  c.prose_stale = true;
  c.include_basics = false;
  c.shared_basics = false;
  c.same_group_size = false;
  await page.goto("/#/tools/word");
  await loadConfig(page, c);
  await page.getByRole("tab", { name: /文字匹配/ }).click();
  await expect(page.getByLabel("研究段落")).toContainText("第二项研究");
  await expect(page.getByLabel("对照组 文字例数")).toHaveValue("20");
  await expect(page.getByLabel("一般资料原文")).toHaveValue(doc.source_text);
  await page.getByRole("tab", { name: /全部字段以及来源/ }).click();
  await expect(page.getByRole("alert")).toContainText("重新识别");
  await expect(
    page.getByText("Word正文（待核对）", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: /生成与导出/ }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("重新识别");
  await page.getByRole("tab", { name: /文字匹配/ }).click();
  await page
    .getByRole("checkbox", { name: "生成时采用文字匹配数据", exact: true })
    .uncheck();
  await page.getByRole("tab", { name: /基础资料/ }).click();
  await expect(
    page.getByRole("checkbox", { name: "包含基础资料与结局列", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("checkbox", { name: "包含基础资料与结局列", exact: true })
    .check();
  await page.getByRole("tab", { name: /文字匹配/ }).click();
  await page
    .getByRole("checkbox", { name: "生成时采用文字匹配数据", exact: true })
    .check();
  await page.getByRole("tab", { name: /基础资料/ }).click();
  await expect(
    page.getByRole("checkbox", { name: "包含基础资料与结局列", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("checkbox", { name: "包含基础资料与结局列", exact: true }),
  ).not.toBeChecked();
});

test("malformed configurations keep the current editors usable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#/tools/shap");
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("800");
  await loadConfig(page, {
    schema_version: 1,
    data: { features: [] },
    plots: { common: {} },
  });
  await expect(page.getByRole("alert")).toContainText("配置不完整");
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("800");
  await page.goto("/#/tools/word");
  await loadConfig(page, { version: 1, groups: [{}] });
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("当前组生成例数")).toHaveValue("70");
  expect(errors).toEqual([]);
});

test("numeric results keep generated precision and generation can be cancelled", async ({
  page,
}) => {
  await page.goto("/#/tools/numeric");
  await page.getByLabel("小数位数", { exact: true }).click();
  await page.getByRole("option", { name: "2", exact: true }).click();
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).not.toHaveValue("");
  const output = await page.getByLabel("全部生成数值").inputValue();
  await page.getByLabel("小数位数", { exact: true }).click();
  await page.getByRole("option", { name: "0", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toHaveValue(output);
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await page.getByRole("button", { name: "停止生成", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "生成模拟数据", exact: true }),
  ).toBeEnabled({ timeout: 30000 });
});

test("single-plot preview never displays another plot and rapid result tabs keep the final table", async ({
  page,
  request,
}) => {
  const c = await defaults(request, "tool.shap.defaults");
  c.data.n_samples = 60;
  c.explanation.background_max_samples = 10;
  c.plots.dpi = 72;
  for (const [name, s] of Object.entries(c.plots.plots) as [string, any][])
    s.enabled = name === "bar";
  await page.goto("/#/tools/shap");
  await loadConfig(page, c);
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("60");
  await page.getByRole("button", { name: "生成完整分析", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存当前图" })).toBeVisible({
    timeout: 90000,
  });
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await page
    .getByRole("button", { name: "特征重要性条形图", exact: true })
    .click();
  await page.getByRole("button", { name: "预览当前样式", exact: true }).click();
  await expect(page.locator(".style-preview img")).toBeVisible({
    timeout: 60000,
  });
  await page.getByRole("button", { name: "单样本力图", exact: true }).click();
  await expect(page.locator(".style-preview img")).toHaveCount(0);
  await page.getByRole("tab", { name: /结果与导出/ }).click();
  await page.route("**/api/bridge", async (route) => {
    if (
      route.request().postDataJSON()?.method === "tool.shap.table" &&
      route.request().postDataJSON()?.params.kind === "data"
    )
      await new Promise((r) => setTimeout(r, 700));
    await route.continue();
  });
  await page.getByRole("button", { name: "模拟数据", exact: true }).click();
  await page.getByRole("button", { name: "模型系数", exact: true }).click();
  await expect(
    page.getByRole("columnheader", { name: "系数", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(900);
  await expect(
    page.getByRole("columnheader", { name: "系数", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "患者ID", exact: true }),
  ).toHaveCount(0);
});

test("large Unicode Word payloads survive Python pipe boundaries", async ({
  request,
}) => {
  const { execFileSync } = await import("node:child_process");
  const python =
    process.env.RESEARCH_V3_PYTHON ||
    resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    );
  const encoded = execFileSync(
    python,
    [
      "-c",
      `import io,base64
from zipfile import ZipFile
from xml.etree import ElementTree as E
w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
r=E.Element(w+'document');b=E.SubElement(r,w+'body');p=E.SubElement(b,w+'p');E.SubElement(E.SubElement(p,w+'r'),w+'t').text='汉字😀边界'*6000
out=io.BytesIO()
with ZipFile(out,'w') as z:z.writestr('word/document.xml',E.tostring(r))
print(base64.b64encode(out.getvalue()).decode())`,
    ],
    { encoding: "utf8" },
  ).trim();
  const response = await request.post("/api/bridge", {
    data: {
      method: "tool.word.scan",
      params: { uploads: [{ name: "Unicode.docx", content: encoded }] },
    },
  });
  const body = await response.json();
  expect(body.ok, body.error).toBe(true);
  expect(body.result.scan.prose_text).toContain("汉字😀边界".repeat(6000));
  expect(body.result.scan.prose_text).not.toContain("\ufffd");
  const text = "汉字😀边界".repeat(6000);
  const parsed = await request.post("/api/bridge", {
    data: { method: "tool.word.prose.parse", params: { text } },
  });
  const parsedBody = await parsed.json();
  expect(parsedBody.ok, parsedBody.error).toBe(true);
  expect(parsedBody.result.source_text).toBe(text);
});
