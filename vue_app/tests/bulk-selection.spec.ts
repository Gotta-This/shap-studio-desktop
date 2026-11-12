import { test, expect } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { changeSelection } from "../src/lib/selection";
const workspace = join(mkdtempSync(join(tmpdir(), "research-v3-bulk-")), "稿件工作空间");
const dataset = {
  name: "批量选择.csv",
  mimeType: "text/csv",
  buffer: Buffer.from(
    "编号,分组,年龄,BMI,术后评分,性别\n" +
      Array.from(
        { length: 40 },
        (_, i) => `P${i},${i % 2},${20 + i},${18 + i / 10},${30 + i},${i % 2}`,
      ).join("\n"),
  ),
};

async function ensureWorkspace(page: import("@playwright/test").Page) {
  await page.goto("/#/settings");
  await page.locator("#workspace-path").fill(workspace);
  await page.locator("form.dialog-form").getByRole("button").click();
  await expect(page.getByText("已连接", { exact: true })).toBeVisible();
}

test("scoped selections preserve hidden items, remove duplicates and invert twice", () => {
  const selected = ["hidden", "A", "A"];
  expect(changeSelection(selected, ["A", "B"], "all")).toEqual([
    "hidden",
    "A",
    "B",
  ]);
  expect(changeSelection(selected, ["A", "B"], "none")).toEqual(["hidden"]);
  expect(changeSelection(selected, ["A", "B"], "invert")).toEqual([
    "hidden",
    "B",
  ]);
  expect(
    new Set(
      changeSelection(
        changeSelection(selected, ["A", "B"], "invert"),
        ["A", "B"],
        "invert",
      ),
    ),
  ).toEqual(new Set(selected));
  expect(changeSelection(["hidden"], [], "all")).toEqual(["hidden"]);
});

test("prediction features and models offer batch selection and tri-state header", async ({
  page,
}) => {
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(dataset);
  const controls = page.getByRole("group", { name: "预测指标批量选择" });
  await expect(controls).toContainText("已选 4/4");
  await controls
    .getByRole("button", { name: "预测指标全不选", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "下一步：设置模型", exact: true }),
  ).toBeDisabled();
  await controls
    .getByRole("button", { name: "预测指标反选", exact: true })
    .click();
  await page.getByRole("checkbox", { name: "使用 BMI", exact: true }).uncheck();
  await expect(
    page.getByRole("checkbox", { name: "全选预测指标", exact: true }),
  ).toHaveAttribute("aria-checked", "mixed");
  await controls
    .getByRole("button", { name: "预测指标反选", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "使用 BMI", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "使用 年龄", exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "使用 编号", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("checkbox", { name: "使用 分组", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("checkbox", { name: "全选预测指标", exact: true })
    .check();
  await expect(controls).toContainText("已选 4/4");
  await page.screenshot({ path: "test-results/prediction-bulk-selection.png" });
  await page
    .getByRole("button", { name: "下一步：设置模型", exact: true })
    .click();
  const models = page.getByRole("group", { name: "预测模型批量选择" });
  await models
    .getByRole("button", { name: "预测模型全不选", exact: true })
    .click();
  await expect(models).toContainText("已选 0/4");
  await models
    .getByRole("button", { name: "预测模型反选", exact: true })
    .click();
  await expect(models).toContainText("已选 4/4");
});

test("style selection keeps edited values and export formats can be selected together", async ({
  page,
}) => {
  await page.goto("/#/tools/prediction");
  await page.getByLabel("导入预测数据").setInputFiles(dataset);
  await page.getByRole("button", { name: "图表设置", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const formats = dialog.getByRole("group", { name: "公共导出格式批量选择" });
  await formats
    .getByRole("button", { name: "公共导出格式全不选", exact: true })
    .click();
  await expect(formats).toContainText("已选 0/3");
  await formats
    .getByRole("button", { name: "公共导出格式反选", exact: true })
    .click();
  await expect(formats).toContainText("已选 3/3");
  await dialog
    .getByRole("button", { name: "SHAP 解释图", exact: true })
    .click();
  await dialog.getByRole("button", { name: "恢复初始样式", exact: true }).click();
  await expect(dialog.getByRole("group", { name: "本图独立导出格式批量选择" })).toContainText("已选 2/3");
  const featureStyles = dialog.getByRole("group", {
    name: "指标独立样式批量选择",
  });
  await featureStyles
    .getByRole("button", { name: "指标独立样式全选", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "shap 年龄 · 显示名称", exact: true })
    .fill("年龄自定义");
  const first = dialog.getByRole("checkbox", {
    name: "单独设置此指标",
    exact: true,
  });
  await first.last().uncheck();
  await featureStyles
    .getByRole("button", { name: "指标独立样式全选", exact: true })
    .click();
  await expect(
    dialog.getByRole("textbox", { name: "shap 年龄 · 显示名称", exact: true }),
  ).toHaveValue("年龄自定义");
  await featureStyles
    .getByRole("button", { name: "指标独立样式反选", exact: true })
    .click();
  await expect(featureStyles).toContainText("已选 0/4");
  await dialog.getByRole("button", { name: "ROC 曲线", exact: true }).click();
  const modelStyles = dialog.getByRole("group", {
    name: "本图模型样式覆盖批量选择",
  });
  await modelStyles
    .getByRole("button", { name: "本图模型样式覆盖全选", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "roc LR · 颜色", exact: true })
    .fill("#123456");
  await dialog
    .getByRole("checkbox", { name: "覆盖 RF 的公共模型样式", exact: true })
    .uncheck();
  await modelStyles
    .getByRole("button", { name: "本图模型样式覆盖全选", exact: true })
    .click();
  await expect(
    dialog.getByRole("textbox", { name: "roc LR · 颜色", exact: true }),
  ).toHaveValue("#123456");
  const visible = dialog.getByRole("group", { name: "本图显示曲线批量选择" });
  await visible
    .getByRole("button", { name: "本图显示曲线全不选", exact: true })
    .click();
  await expect(visible).toContainText("已选 0/4");
  await visible
    .getByRole("button", { name: "本图显示曲线反选", exact: true })
    .click();
  await expect(visible).toContainText("已选 4/4");
  await expect(
    dialog.getByRole("textbox", { name: "roc LR · 颜色", exact: true }),
  ).toHaveValue("#123456");
});

test("inbox batch actions and header preserve selections outside the search", async ({
  page,
}) => {
  const tag = Date.now().toString();
  const a = `bulk-${tag}-alpha.txt`,
    b = `bulk-${tag}-beta.txt`;
  await ensureWorkspace(page);
  await page.goto("/#/inbox");
  await page
    .getByRole("button", { name: "接收材料", exact: true })
    .first()
    .click();
  await page.getByLabel("选择导入材料").setInputFiles([
    { name: a, mimeType: "text/plain", buffer: Buffer.from("alpha" + tag) },
    { name: b, mimeType: "text/plain", buffer: Buffer.from("beta" + tag) },
  ]);
  await page.getByRole("button", { name: /确认导入/ }).click();
  await expect(
    page.getByRole("checkbox", { name: "选择 " + a, exact: true }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "选择 " + a, exact: true }).check();
  await page.getByLabel("搜索收件箱").fill(b);
  const actions = page.getByRole("group", { name: "待归档材料批量选择" });
  await expect(actions).toContainText("范围外另选 1 项");
  await actions
    .getByRole("button", { name: "待归档材料全选", exact: true })
    .click();
  await actions
    .getByRole("button", { name: "待归档材料反选", exact: true })
    .click();
  await page.getByLabel("搜索收件箱").fill(a);
  await expect(
    page.getByRole("checkbox", { name: "选择 " + a, exact: true }),
  ).toBeChecked();
  await page.getByLabel("搜索收件箱").fill(b);
  await page
    .getByRole("checkbox", { name: "全选待归档材料", exact: true })
    .check();
  await page
    .getByRole("checkbox", { name: "全选待归档材料", exact: true })
    .uncheck();
  await page.getByLabel("搜索收件箱").fill(a);
  await expect(
    page.getByRole("checkbox", { name: "选择 " + a, exact: true }),
  ).toBeChecked();
});

test("workspace columns and todo linked materials support batch selection", async ({
  page,
}) => {
  await ensureWorkspace(page);
  await page.goto("/#/workspace");
  await page.getByRole("button", { name: "显示列", exact: true }).click();
  const columns = page.getByRole("group", { name: "显示列批量选择" });
  await columns
    .getByRole("button", { name: "显示列全不选", exact: true })
    .click();
  await expect(
    page.getByRole("columnheader", { name: "标签", exact: true }),
  ).toHaveCount(0);
  await columns
    .getByRole("button", { name: "显示列反选", exact: true })
    .click();
  await expect(
    page.getByRole("columnheader", { name: "标签", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "新建任务", exact: true })
    .first()
    .click();
  await page.getByLabel("客户 / 甲方").fill("批量选择验收");
  await page.getByLabel("任务名称").fill("关联材料验收" + Date.now());
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await page
    .getByRole("button", { name: "导入材料", exact: true })
    .first()
    .click();
  await page.getByLabel("选择导入材料").setInputFiles([
    { name: "材料甲.txt", mimeType: "text/plain", buffer: Buffer.from("a") },
    { name: "材料乙.txt", mimeType: "text/plain", buffer: Buffer.from("b") },
  ]);
  await page.getByRole("button", { name: /确认导入/ }).click();
  await page
    .getByRole("button", { name: "新增下一步工作", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  const materials = dialog.getByRole("group", { name: "关联材料批量选择" });
  await materials
    .getByRole("button", { name: "关联材料全选", exact: true })
    .click();
  await expect(materials).toContainText("已选 2/2");
  await dialog
    .getByRole("checkbox", { name: "材料甲.txt", exact: true })
    .uncheck();
  await materials
    .getByRole("button", { name: "关联材料反选", exact: true })
    .click();
  await expect(
    dialog.getByRole("checkbox", { name: "材料甲.txt", exact: true }),
  ).toBeChecked();
  await expect(
    dialog.getByRole("checkbox", { name: "材料乙.txt", exact: true }),
  ).not.toBeChecked();
  await dialog.locator("#todo-text").fill("核对关联材料甲");
  await dialog.getByRole("button", { name: "保存待办", exact: true }).click();
  await expect(page.getByText("核对关联材料甲", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /核对关联材料甲/ }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("checkbox", { name: "材料甲.txt", exact: true }),
  ).toBeChecked();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("checkbox", { name: "材料乙.txt", exact: true }),
  ).not.toBeChecked();
});

test("fourth tool formats and inherited styles keep custom values on select all", async ({
  page,
}) => {
  await page.goto("/#/tools/shap");
  await page.getByRole("tab", { name: /图表样式/ }).click();
  const formats = page.getByRole("group", { name: "图片导出格式批量选择" });
  await formats
    .getByRole("button", { name: "图片导出格式全不选", exact: true })
    .click();
  await formats
    .getByRole("button", { name: "图片导出格式反选", exact: true })
    .click();
  await expect(formats).toContainText("已选 3/3");
  const nav = page.locator(".style-navigation");
  const plotButtons = nav.locator("button");
  await plotButtons.nth(1).click();
  const styles = page.getByRole("group", { name: "独立样式属性批量选择" });
  await styles
    .getByRole("button", { name: "独立样式属性全选", exact: true })
    .click();
  const font = page.getByLabel("字体列表", { exact: true });
  await font.fill("Arial, Songti SC");
  await page
    .getByRole("checkbox", { name: "独立设置 标题字号", exact: true })
    .uncheck();
  await styles
    .getByRole("button", { name: "独立样式属性全选", exact: true })
    .click();
  await expect(font).toHaveValue("Arial, Songti SC");
  await styles
    .getByRole("button", { name: "独立样式属性反选", exact: true })
    .click();
  await expect(font).toBeDisabled();
  await page.screenshot({ path: "test-results/shap-style-bulk-selection.png" });
});
