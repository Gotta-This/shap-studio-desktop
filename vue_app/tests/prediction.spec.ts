import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
function fixture(bad = false) {
  return execFileSync(
    process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python"),
    [
      "-c",
      `import numpy as np,pandas as pd,tempfile
from pathlib import Path
r=np.random.default_rng(17);n=120;a=r.normal(50,10,n);s=r.choice(['女','男'],n);y=(r.random(n)<1/(1+np.exp(-(a-50)/15))).astype(int)
p=Path(tempfile.mkdtemp())/'预测测试.xlsx'
d=pd.DataFrame({'编号':[f'P{i}' for i in range(n)],'分组':y,'年龄':a,'性别':s})
${bad ? "d.loc[1,'编号']=d.loc[0,'编号']" : "d.loc[0,'年龄']=np.nan"}
d.to_excel(p,index=False);print(p)`,
    ],
    { encoding: "utf8" },
  ).trim();
}
test("fifth tool imports, trains four models, previews and exports complete results", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "科研工具" })
    .getByRole("link", { name: "预测模型分析" })
    .click();
  await expect(
    page.getByRole("heading", { name: "临床二分类预测模型分析" }),
  ).toBeVisible();
  await page.getByLabel("导入预测数据").setInputFiles(fixture());
  await expect(page.getByText("120 例 · 4 列 · 已选 2 项指标")).toBeVisible();
  await page.getByRole("button", { name: "下一步：设置模型" }).click();
  await expect(page.getByText(/预计训练 84 例／验证 36 例/)).toBeVisible();
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "分析完成", exact: true }),
  ).toBeVisible({ timeout: 150000 });
  await expect(page.getByRole("row")).toHaveCount(9);
  await expect(page.getByRole("img", { name: "ROC_训练与验证" })).toBeVisible();
  await page
    .getByRole("button", { name: "校准_训练与验证", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "校准_训练与验证" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "LR列线图", exact: true }).click();
  await expect(page.getByRole("img", { name: "LR列线图" })).toBeVisible();
  await page
    .getByRole("img", { name: "LR列线图" })
    .screenshot({ path: "test-results/prediction-nomogram.png" });
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出完整结果 ZIP" }).click();
  const d = await pending;
  expect(d.suggestedFilename()).toBe("完整分析结果.zip");
  await page.screenshot({
    path: "test-results/prediction-results.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation", { name: "科研工具" })
    .getByRole("link", { name: "自定义类别数列" })
    .click();
  await page
    .getByRole("navigation", { name: "科研工具" })
    .getByRole("link", { name: "预测模型分析" })
    .click();
  await expect(
    page.getByRole("heading", { name: "分析完成", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("duplicate IDs report an error and settings remain recoverable", async ({
  page,
}) => {
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(fixture(true));
  await page.getByRole("button", { name: "下一步：设置模型" }).click();
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("重复");
  await page.getByRole("button", { name: "返回设置", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "划分数据与模型设置" }),
  ).toBeVisible();
});
test("compact small-window layout and empty selection are usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 780, height: 800 });
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(fixture());
  await page.getByRole("checkbox", { name: "使用 年龄", exact: true }).click();
  await page.getByRole("checkbox", { name: "使用 性别", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "下一步：设置模型" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/prediction-small.png",
    fullPage: true,
  });
});

test("count split, model selection and cooperative cancellation recover", async ({
  page,
}) => {
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(fixture());
  await page.getByRole("button", { name: "下一步：设置模型" }).click();
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: "指定训练例数" }).click();
  await page.getByRole("spinbutton", { name: "训练例数" }).fill("80");
  await expect(page.getByText(/预计训练 80 例／验证 40 例/)).toBeVisible();
  for (const name of [
    "Logistic 回归（LR）",
    "随机森林（RF）",
    "XGBoost（XGB）",
    "支持向量机（SVM）",
  ])
    await page.getByRole("checkbox", { name, exact: true }).uncheck();
  await expect(
    page.getByRole("button", { name: "开始分析", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", { name: "随机森林（RF）", exact: true })
    .check();
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await page.getByRole("button", { name: "取消分析", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "返回设置", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("heading", { name: "分析完成", exact: true }),
  ).toHaveCount(0);
});
