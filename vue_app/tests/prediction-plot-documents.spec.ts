import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const defaults = JSON.parse(
  readFileSync(
    new URL("../python/prediction_plot_defaults.json", import.meta.url),
    "utf8",
  ),
);
import { predictionPlotDocuments } from "../src/lib/predictionPlotDocuments";

test("descriptions and prompts reflect per-plot overrides and distinguish actual exports", () => {
  const c: any = structuredClone(defaults);
  c.common.dpi = 720;
  c.models.RF.color = "#abcdef";
  c.model_order = ["RF", "LR", "XGB", "SVM"];
  c.plots.shap.style = { ...c.plots.shap.style, dpi: 320, title_size: 23 };
  c.plots.shap.point_size = 4;
  c.plots.nomogram.label_size = 15;
  c.plots.nomogram.tick_size = 8;
  const docs = predictionPlotDocuments(c, [
    {
      name: "SHAP解释组合图",
      dpi: 280,
      requested_dpi: 650,
      width_inches: 12,
      height_inches: 16,
      preview_dpi: 110,
      formats: ["png", "pdf"],
      png_pixels: [3360, 4480],
    },
  ]);
  expect(docs.description).toContain("全图请求导出 DPI：720");
  expect(docs.description).toContain("本图请求导出 DPI：320");
  expect(docs.description).toContain("总标题：23 pt");
  expect(docs.description).toContain("散点面积：4 pt²");
  expect(docs.description).toContain("RF → LR → XGB → SVM");
  expect(docs.description).toContain("#abcdef");
  expect(docs.description).toContain(
    "列线图变量名和轴名称实际字号：15 pt；数值刻度：8 pt",
  );
  expect(docs.description).toContain("上一次导出记录");
  expect(docs.description).toContain("PNG 实际 280 DPI（请求 650 DPI）");
  expect(docs.description).toContain("3360 × 4480 像素");
  expect(JSON.parse(docs.json)).toEqual(c);
  expect(docs.prompt).toContain(docs.description);
  expect(docs.prompt).toContain(docs.json);
  expect(docs.prompt).toContain("不重新训练或修改预测概率");
  expect(predictionPlotDocuments(c).description).toContain(
    "最近实际导出：尚无记录",
  );
});

test("configuration screen copies all formats, follows JSON edits and rejects invalid config", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const starts: string[] = [];
  page.on("request", (request) => {
    if (
      request.url().endsWith("/api/bridge") &&
      request.postDataJSON().method === "tool.job.start"
    )
      starts.push(request.postDataJSON().params.kind);
  });
  await page.goto("/#/tools/prediction");
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("spinbutton", { name: "导出 DPI", exact: true })
    .fill("333");
  await dialog
    .getByRole("button", { name: "完整配置 JSON", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "中文参数说明", exact: true })
    .click();
  const description = dialog.getByRole("textbox", {
    name: "中文参数说明",
    exact: true,
  });
  await expect(description).toHaveValue(/全图请求导出 DPI：333/);
  await expect(description).toHaveAttribute("readonly", "");
  await dialog
    .getByRole("button", { name: "复制中文参数说明", exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toContain("全图请求导出 DPI：333");
  await dialog
    .getByRole("button", { name: "AI 作图提示词", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "复制AI 作图提示词", exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toContain("严格采用以下配置与版式");
  await dialog.getByRole("button", { name: "JSON 配置", exact: true }).click();
  const editor = dialog.getByRole("textbox", {
    name: "完整图表配置 JSON",
    exact: true,
  });
  const changed = JSON.parse(await editor.inputValue());
  changed.common.dpi = 444;
  await editor.fill(JSON.stringify(changed));
  await dialog
    .getByRole("button", { name: "中文参数说明", exact: true })
    .click();
  await expect(description).toHaveValue(/全图请求导出 DPI：444/);
  await dialog.getByRole("button", { name: "JSON 配置", exact: true }).click();
  await dialog
    .getByRole("button", { name: "复制JSON 配置", exact: true })
    .click();
  await expect
    .poll(async () => {
      try {
        return JSON.parse(
          await page.evaluate(() => navigator.clipboard.readText()),
        ).common.dpi;
      } catch {
        return null;
      }
    })
    .toBe(444);
  await editor.fill('{"common":');
  await dialog
    .getByRole("button", { name: "AI 作图提示词", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "复制AI 作图提示词", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("textbox", { name: "AI 作图提示词", exact: true }),
  ).toHaveValue("");
  expect(starts).toEqual([]);
  await dialog.getByRole("button", { name: "JSON 配置", exact: true }).click();
  await editor.fill(JSON.stringify({ ...changed, unsupported: 1 }));
  await dialog
    .getByRole("button", { name: "复制JSON 配置", exact: true })
    .click();
  await expect(dialog.getByText(/不支持的图表设置/)).toBeVisible();
  await editor.fill(JSON.stringify(changed));
  await page.setViewportSize({ width: 800, height: 600 });
  await dialog
    .getByRole("button", { name: "中文参数说明", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "复制中文参数说明", exact: true }),
  ).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "应用设置", exact: true }),
  ).toBeInViewport();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await dialog.screenshot({ path: "test-results/config-description.png" });
});
