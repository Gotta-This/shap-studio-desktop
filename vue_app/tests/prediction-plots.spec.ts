import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const python = () =>
  process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python");
function fixture() {
  return execFileSync(
    python(),
    [
      "-c",
      `import tempfile
from pathlib import Path
p=Path(tempfile.mkdtemp())/'图表样式测试.csv'
p.write_text('编号,分组,年龄,性别\\n'+'\\n'.join(f'P{i},{i%2},{20+i%60},{"女" if i%3 else "男"}' for i in range(120)),encoding='utf-8-sig')
print(p)`,
    ],
    { encoding: "utf8" },
  ).trim();
}
test("all style sections affect generated files and redraw does not start another training job", async ({
  page,
}) => {
  test.setTimeout(180000);
  const starts: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.url().endsWith("/api/bridge")) {
      const p = r.postDataJSON();
      if (p.method === "tool.job.start") starts.push(p.params.kind);
    }
  });
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(fixture());
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("spinbutton", { name: "导出 DPI", exact: true })
    .fill("100");
  await dialog.getByRole("checkbox", { name: "SVG", exact: true }).check();
  await dialog
    .getByRole("button", { name: "模型与图例顺序", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "RF · 显示名称", exact: true })
    .fill("Forest custom");
  await dialog
    .getByRole("textbox", { name: "RF · 颜色", exact: true })
    .fill("#ff1122");
  await dialog.getByRole("button", { name: "RF 上移", exact: true }).click();
  await dialog.getByRole("button", { name: "ROC 曲线", exact: true }).click();
  await dialog
    .getByRole("textbox", { name: "roc · 总标题", exact: true })
    .fill("Custom ROC");
  await dialog
    .getByRole("textbox", {
      name: "roc · 导出文件名（不含扩展名）",
      exact: true,
    })
    .fill("CustomROC");
  await dialog
    .getByRole("textbox", { name: "roc · X 轴标题", exact: true })
    .fill("Custom Specificity");
  await dialog.getByRole("button", { name: "校准曲线", exact: true }).click();
  await dialog
    .getByRole("textbox", { name: "calibration · 总标题", exact: true })
    .fill("Custom Calibration");
  await dialog.getByRole("button", { name: "LR 列线图", exact: true }).click();
  await dialog
    .getByRole("textbox", { name: "nomogram · 总标题", exact: true })
    .fill("Custom Nomogram");
  await dialog
    .getByRole("button", { name: "指标顺序与颜色", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "性别 指标上移", exact: true })
    .click();
  await dialog
    .getByRole("textbox", {
      name: "性别 · 显示名称（留空使用原名）",
      exact: true,
    })
    .fill("Gender custom");
  await dialog
    .getByRole("textbox", { name: "性别 · 指标颜色", exact: true })
    .fill("#1245ab");
  await dialog
    .getByRole("textbox", { name: "性别 女 显示名称", exact: true })
    .fill("Female");
  await dialog.screenshot({
    path: "test-results/prediction-plot-feature-settings.png",
  });
  await dialog.getByRole("button", { name: "应用设置", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "下一步：设置模型" }).click();
  await page.getByRole("button", { name: "开始分析", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "分析完成", exact: true }),
  ).toBeVisible({ timeout: 120000 });
  await expect(
    page.getByRole("img", { name: "CustomROC", exact: true }),
  ).toBeVisible();
  const before = await page
    .locator(".prediction-results .data-table")
    .innerText();
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  await dialog.getByRole("button", { name: "公共样式", exact: true }).click();
  await dialog
    .getByRole("spinbutton", { name: "导出 DPI", exact: true })
    .fill("160");
  await dialog
    .getByRole("button", { name: "应用并重新绘图", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "仅重新绘图", exact: true }),
  ).toBeEnabled({ timeout: 60000 });
  await expect(page.getByText(/公共导出 DPI 为 160/)).toBeVisible();
  expect(
    await page.locator(".prediction-results .data-table").innerText(),
  ).toBe(before);
  expect(starts).toEqual(["prediction", "prediction_plot"]);
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出完整结果 ZIP", exact: true })
    .click();
  const download = await pending;
  const path = await download.path();
  const check = JSON.parse(
    execFileSync(
      python(),
      [
        "-c",
        `import sys,json,io
from zipfile import ZipFile
from PIL import Image
with ZipFile(sys.argv[1]) as z:
 c=json.loads(z.read('图表设置.json'));s=z.read('CustomROC.svg').decode();n=z.read('LR列线图.svg').decode()
 im=Image.open(io.BytesIO(z.read('CustomROC.png')))
 print(json.dumps(dict(dpi=im.info['dpi'][0],model_order=c['model_order'],roc='Custom ROC' in s,color='#ff1122' in s,feature='Gender custom' in n,feature_color='#1245ab' in n,note='Custom Calibration' in z.read('校准_训练与验证.svg').decode())))`,
        path!,
      ],
      { encoding: "utf8" },
    ),
  );
  expect(check.dpi).toBeCloseTo(160, 0);
  expect(check.model_order[0]).toBe("RF");
  expect(
    check.roc &&
      check.color &&
      check.feature &&
      check.feature_color &&
      check.note,
  ).toBeTruthy();
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  await dialog
    .getByRole("button", { name: "完整配置 JSON", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "中文参数说明", exact: true })
    .click();
  await expect(
    dialog.getByRole("textbox", { name: "中文参数说明", exact: true }),
  ).toHaveValue(/CustomROC：.*PNG 实际 160 DPI/);
  await expect(
    dialog.getByRole("textbox", { name: "中文参数说明", exact: true }),
  ).toHaveValue(/上一次导出记录/);
  expect(errors).toEqual([]);
});
test("invalid JSON is rejected and a saved default can be restored across reload", async ({
  page,
  request,
}) => {
  await page.goto("/#/tools/prediction");
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "完整配置 JSON", exact: true })
    .click();
  const input = dialog.getByRole("textbox", { name: "完整图表配置 JSON" });
  await input.fill("{broken");
  await dialog.getByRole("button", { name: "应用设置", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog
    .getByRole("button", { name: "恢复初始样式", exact: true })
    .click();
  await dialog.getByRole("button", { name: "公共样式", exact: true }).click();
  await dialog
    .getByRole("spinbutton", { name: "导出 DPI", exact: true })
    .fill("180");
  await dialog.getByRole("button", { name: "保存为默认", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("已保存为第五个工具");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  try {
    await page.reload();
    await page.getByRole("button", { name: "图表设置", exact: true }).click();
    await expect(
      page.getByRole("spinbutton", { name: "导出 DPI", exact: true }),
    ).toHaveValue("180");
  } finally {
    await request.post("/api/bridge", {
      data: { method: "tool.prediction.plot.save", params: { config: {} } },
    });
  }
});

test("small-window settings keep the apply action visible while options scroll", async ({
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 600 });
  await page.goto("/#/tools/prediction");
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "ROC 曲线", exact: true }).click();
  const apply = dialog.getByRole("button", { name: "应用设置", exact: true });
  await expect(apply).toBeInViewport();
  await expect(
    dialog.getByRole("textbox", {
      name: "roc · 导出文件名（不含扩展名）",
      exact: true,
    }),
  ).toBeVisible();
  await dialog.screenshot({ path: "test-results/prediction-plot-small.png" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
