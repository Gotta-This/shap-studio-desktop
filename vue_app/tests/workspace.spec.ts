import { test, expect } from "@playwright/test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
const fixture = mkdtempSync(join(tmpdir(), "research-v3-e2e-"));
const workspace = join(fixture, "稿件工作空间");
test.describe.configure({ mode: "serial" });
test.beforeAll(() =>
  rmSync(resolve(".v3-data/browser-tests"), { recursive: true, force: true }),
);
const errors: string[] = [];
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
});
test("connect workspace, create, search, edit date, upload, preview and complete todo", async ({
  page,
}) => {
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await page.getByLabel("选择存放新稿件的文件夹").fill(workspace);
  await page.getByRole("button", { name: "启用工作空间", exact: true }).click();
  await expect(page.getByText("已连接", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /稿件工作空间/ }).click();
  await page
    .getByRole("button", { name: "新建任务", exact: true })
    .first()
    .click();
  await page.getByLabel("客户 / 甲方").fill("Vue 巡检客户");
  await page.getByLabel("任务名称").fill("V3 冠心病论文返修");
  await page.getByLabel("标签", { exact: true }).fill("预测模型，返修");
  await page.locator("#first-todo").fill("核对原稿与图表");
  await page.getByRole("button", { name: "任务截止日期", exact: true }).click();
  await page.getByLabel("输入日期").fill("2027-02-29");
  await page.getByLabel("输入日期").press("Enter");
  await expect(
    page.getByText("请输入有效日期，例如 2028-02-29。"),
  ).toBeVisible();
  await page.getByLabel("输入日期").fill("2028-02-29");
  await page.getByLabel("输入日期").press("Enter");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "V3 冠心病论文返修", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "导入材料", exact: true })
    .first()
    .click();
  await page.getByLabel("选择导入材料").setInputFiles({
    name: "审稿意见.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("请核对图表与统计值。"),
  });
  await page.getByRole("button", { name: /确认导入/ }).click();
  await expect(
    page.getByText("审稿意见.txt", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await expect(page.getByText("请核对图表与统计值。")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("checkbox", { name: "完成 核对原稿与图表" }).check();
  await expect(page.getByText("已完成 · 普通优先级")).toBeVisible();
  await page.getByRole("button", { name: "编辑任务", exact: true }).click();
  await page.getByLabel("任务名称").fill("V3 冠心病论文 · 第二轮");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "V3 冠心病论文 · 第二轮" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: "完成 核对原稿与图表" }),
  ).toBeChecked();
  await page.screenshot({
    path: "test-results/v3-task-detail.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "全部任务", exact: true }).click();
  await page.getByLabel("搜索稿件任务").fill("不存在的客户");
  await expect(page.getByText("没有找到匹配的任务")).toBeVisible();
  await page.getByLabel("搜索稿件任务").fill("审稿意见");
  await expect(
    page.getByText("V3 冠心病论文 · 第二轮", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/v3-workspace.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
test("personal todo date, escape, complete, delete and undo", async ({
  page,
}) => {
  await page.getByRole("link", { name: /待办事项/ }).click();
  await page
    .getByRole("button", { name: "新增待办", exact: true })
    .first()
    .click();
  await page.getByLabel("下一步工作 *").fill("独立待办日期测试");
  await page.getByRole("button", { name: "待办截止日期", exact: true }).click();
  await page.getByLabel("输入日期").fill("2028-03-02");
  await page.getByLabel("输入日期").press("Enter");
  await page.getByRole("button", { name: "保存待办", exact: true }).click();
  await expect(
    page.getByText("独立待办日期测试", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "修改截止日期 独立待办日期测试" })
    .click();
  await page.getByLabel("输入日期").fill("2030-12-30");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "修改截止日期 独立待办日期测试" }),
  ).toContainText("2028-03-02");
  await page.getByRole("button", { name: "待办操作 独立待办日期测试" }).click();
  await page.getByRole("menuitem", { name: "删除待办" }).click();
  await expect(
    page.getByRole("button", { name: "撤销", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(
    page.getByText("独立待办日期测试", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("inbox import, archive and undo from task operation history", async ({
  page,
}) => {
  await page.getByRole("link", { name: /未分类收件箱/ }).click();
  await page
    .getByRole("button", { name: "接收材料", exact: true })
    .first()
    .click();
  await page.getByLabel("选择导入材料").setInputFiles({
    name: "待归档数据.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("组别,数值\n对照,1\n试验,2"),
  });
  await page.getByRole("button", { name: /确认导入/ }).click();
  await expect(page.getByText("待归档数据.csv", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "选择 待归档数据.csv" }).check();
  await page.getByRole("button", { name: /归档到任务/ }).click();
  await page.getByRole("combobox", { name: "材料归属任务" }).click();
  await page.getByRole("option", { name: /Vue 巡检客户/ }).click();
  await page.getByRole("button", { name: /确认归档/ }).click();
  await expect(page.getByText("收件箱很整洁")).toBeVisible();
  expect(errors).toEqual([]);
});
test("numeric engines generate real results and retain independent module state", async ({
  page,
}) => {
  await page.getByRole("link", { name: "自定义类别数列", exact: true }).click();
  await page.getByRole("button", { name: "生成随机数列", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).not.toHaveValue("");
  const result = await page.getByLabel("全部生成数值").inputValue();
  expect(result.split("\n")).toHaveLength(121);
  await page
    .getByRole("link", { name: "均数 / 标准差模拟", exact: true })
    .click();
  await page.getByLabel("例数", { exact: true }).fill("20");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).not.toHaveValue("");
  expect(
    (await page.getByLabel("全部生成数值").inputValue()).split("\n"),
  ).toHaveLength(20);
  await page.getByRole("link", { name: "自定义类别数列", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).toHaveValue(result);
  expect(errors).toEqual([]);
});
test("all tool pages, global search, mobile layout and screenshots", async ({
  page,
}) => {
  await page.getByRole("link", { name: "Word 转 Excel", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Word 一键生成 Excel" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "模拟数据生图", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "数据参数", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: /模型与分类变量/ }).click();
  await expect(
    page.getByRole("heading", { name: "模型与分类变量", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: /图表样式/ }).click();
  await expect(
    page.getByRole("heading", { name: "图表样式", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "工作台", exact: true }).click();
  await page.screenshot({
    path: "test-results/v3-dashboard.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "搜索任务与文件", exact: true })
    .click();
  await page.getByLabel("全局搜索").fill("审稿意见");
  await expect(
    page.getByText("V3 冠心病论文 · 第二轮", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 800, height: 900 });
  await page.getByRole("link", { name: /稿件工作空间/ }).click();
  await page.screenshot({
    path: "test-results/v3-compact.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
