import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
function fixture() {
  return execFileSync(
    process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python"),
    [
      "-c",
      `import tempfile,numpy as np,pandas as pd
from pathlib import Path
r=np.random.default_rng(71);n=100;x=r.normal(size=n);z=r.choice(['A','B','C'],n);y=r.binomial(1,1/(1+np.exp(-x)))
p=Path(tempfile.mkdtemp())/'可选分析.csv';pd.DataFrame({'编号':[f'P{i}' for i in range(n)],'分组':y,'评分':x,'治疗类型':z}).to_csv(p,index=False);print(p)`,
    ],
    { encoding: "utf8" },
  ).trim();
}
test("optional LASSO and SHAP generate real figures, tables and remain style configurable", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(fixture());
  await page.getByRole("button", { name: "下一步：设置模型" }).click();
  await expect(
    page.getByRole("checkbox", { name: "启用 LASSO 筛选诊断", exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "启用 SHAP 模型解释", exact: true }),
  ).not.toBeChecked();
  await page
    .getByRole("checkbox", { name: "启用 LASSO 筛选诊断", exact: true })
    .check();
  await page
    .getByRole("spinbutton", { name: "λ 网格数量", exact: true })
    .fill("8");
  await page
    .getByRole("checkbox", { name: "启用 SHAP 模型解释", exact: true })
    .check();
  await page
    .getByRole("spinbutton", { name: "SHAP 最多解释样本数", exact: true })
    .fill("20");
  await page
    .getByRole("textbox", { name: "SHAP 单病例编号", exact: true })
    .fill("P12");
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "公共样式", exact: true }).click();
  await dialog
    .getByRole("spinbutton", { name: "导出 DPI", exact: true })
    .fill("100");
  await dialog
    .getByRole("button", { name: "LASSO 筛选图", exact: true })
    .click();
  await expect(
    dialog.getByRole("textbox", { name: "lasso · 系数轨迹标题", exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("textbox", { name: "lasso · 系数轨迹标题", exact: true })
    .fill("LASSO custom path");
  await dialog
    .getByRole("button", { name: "SHAP 解释图", exact: true })
    .click();
  await dialog.getByRole("button", { name: "应用最终 SHAP 参考版式", exact: true }).click();
  await expect(dialog.getByRole("spinbutton", { name: "shap · 蜂群点大小", exact: true })).toHaveValue("2.5");
  await dialog
    .getByRole("textbox", { name: "shap · 默认重要性条形颜色", exact: true })
    .fill("#226644");
  await dialog.getByRole("button", { name: "LR 列线图", exact: true }).click();
  await dialog
    .getByRole("button", { name: "应用参考图版式", exact: true })
    .click();
  await dialog.getByRole("button", { name: "应用设置", exact: true }).click();
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "分析完成", exact: true }),
  ).toBeVisible({ timeout: 120000 });
  await expect(
    page.getByRole("heading", { name: "LASSO 筛选建议", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/单病例编号 P12/)).toBeVisible();
  await page.getByRole("button", { name: "LASSO筛选", exact: true }).click();
  await expect(
    page.getByRole("img", { name: "LASSO筛选", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("img", { name: "LASSO筛选", exact: true })
    .screenshot({ path: "test-results/optional-lasso.png" });
  await page
    .getByRole("button", { name: "SHAP解释组合图", exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: "SHAP解释组合图", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("img", { name: "SHAP解释组合图", exact: true })
    .screenshot({ path: "test-results/optional-shap.png" });
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出结果 Excel", exact: true })
    .click();
  const file = await download;
  const path = await file.path();
  const sheets = JSON.parse(
    execFileSync(
      process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python"),
      [
        "-c",
        "import pandas as pd,json,sys; print(json.dumps(pd.ExcelFile(sys.argv[1]).sheet_names))",
        path!,
      ],
      { encoding: "utf8" },
    ),
  );
  expect(sheets).toContain("LASSO交叉验证");
  expect(sheets).toContain("SHAP逐例贡献");
  expect(errors).toEqual([]);
});
