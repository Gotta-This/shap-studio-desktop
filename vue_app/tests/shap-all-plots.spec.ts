import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
test("all six real plots, metrics, zoom and PNG/SVG/PDF export", async ({
  page,
  request,
}) => {
  test.setTimeout(150000);
  const response = await request.post("/api/bridge", {
      data: { method: "tool.shap.defaults", params: {} },
    }),
    config = (await response.json()).result;
  config.data.n_samples = 80;
  config.explanation.background_max_samples = 10;
  config.plots.dpi = 72;
  config.plots.formats = ["png", "svg", "pdf"];
  await page.goto("/#/tools/shap");
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "六图.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
  await expect(page.getByLabel("样本量", { exact: true })).toHaveValue("80");
  await page.getByRole("button", { name: "生成完整分析", exact: true }).click();
  await expect(page.getByRole("button", { name: "保存当前图" })).toBeVisible({
    timeout: 100000,
  });
  await expect(page.getByLabel("结果图选择")).toHaveText(
    await page.locator("img.result-figure").getAttribute("alt") || "missing image",
  );
  for (const style of Object.values(config.plots.plots) as any[]) {
    await page.getByLabel("结果图选择").click();
    await page
      .getByRole("option", { name: style.filename + ".png", exact: true })
      .click();
    await expect(page.locator("img.result-figure")).toHaveAttribute(
      "alt",
      style.filename + ".png",
    );
  }
  await page.getByRole("button", { name: "放大查看", exact: true }).click();
  await expect(page.getByRole("dialog").locator("img")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "模型指标", exact: true }).click();
  await expect(
    page.getByText("训练集", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "颜色核对", exact: true }),
  ).toBeVisible();
  const saving = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存所选内容", exact: true }).click();
  const file = await (await saving).path();
  const python =
    process.env.RESEARCH_V3_PYTHON ||
    resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    );
  const output = execFileSync(
    python,
    [
      "-c",
      `import zipfile,json,sys
with zipfile.ZipFile(sys.argv[1]) as z:
 names=z.namelist()
 for ext in ('.png','.svg','.pdf'):assert len([n for n in names if '/figures/' in n and n.endswith(ext)])==6,(ext,names)
 assert any(n.endswith('parameters.json') for n in names)
 assert any(n.endswith('metrics.json') for n in names)
 assert any(n.endswith('data.csv') for n in names)
 print('six plots in three formats and complete analysis artifacts verified')`,
      file!,
    ],
    { encoding: "utf8" },
  );
  expect(output).toContain("verified");
  await page.screenshot({
    path: "test-results/v3-shap-all-plots.png",
    fullPage: true,
  });
});
