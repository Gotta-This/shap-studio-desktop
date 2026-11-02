import { test, expect } from "@playwright/test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

test("compact Word rules preserve precision and expose edit/remove buttons", async ({
  page,
  request,
}) => {
  const response = await request.post("/api/bridge", {
    data: { method: "tool.word.defaults" },
  });
  const config = (await response.json()).result;
  config.groups = [{ ...config.groups[0], name: "干预组", n: 37 }];
  config.include_basics = false;
  config.typed_fields = [
    {
      table: 1,
      name: "性别/例",
      group: "干预组",
      kind: "gender",
      labels: ["男", "女"],
      weights: [56.75675675675676, 43.24324324324324],
      confirmed: true,
      raw: "21/16",
    },
  ];
  await page.goto("/#/tools/word");
  await page
    .locator('input[type=file][accept=".json"]')
    .setInputFiles({
      name: "参数.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(config)),
    });
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  const row = page.locator(".word-fields-table tbody tr").first();
  await expect(row.locator(".word-rule-lines > span")).toHaveText([
    "男 56.76%",
    "女 43.24%",
  ]);
  const layout = await row.evaluate((row) => {
    const edit = row.querySelector(".word-rule-cell button")!;
    const remove = row.querySelector(".remove-indicator")!;
    const lines = row.querySelector(".word-rule-lines")!;
    return {
      height: row.getBoundingClientRect().height,
      header: document.querySelector(".page-heading")!.getBoundingClientRect()
        .height,
      editBorder: getComputedStyle(edit).borderTopWidth,
      removeBorder: getComputedStyle(remove).borderTopWidth,
      editX: edit.getBoundingClientRect().x,
      linesRight: lines.getBoundingClientRect().right,
    };
  });
  expect(layout.height).toBeLessThan(68);
  expect(layout.header).toBeLessThan(68);
  expect(layout.editBorder).toBe("1px");
  expect(layout.removeBorder).toBe("1px");
  expect(layout.editX).toBeGreaterThan(layout.linesRight);
  const saving = page.waitForEvent("download");
  await page.getByRole("button", { name: "保存配置", exact: true }).click();
  const saved = JSON.parse(
    readFileSync((await (await saving).path())!, "utf8"),
  );
  expect(saved.typed_fields[0].weights).toEqual(config.typed_fields[0].weights);
  await row.getByRole("button", { name: /编辑规则/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await row.getByRole("button", { name: "移除同名指标", exact: true }).click();
  await expect(page.locator(".word-fields-table tbody tr")).toHaveCount(0);
});

const corpus = resolve("../word");
const folder = existsSync(corpus)
  ? readdirSync(corpus).find((name) => name.startsWith("6.03修回-杨见萍"))
  : undefined;
const source = folder
  ? resolve(
      corpus,
      folder,
      readdirSync(resolve(corpus, folder)).find((name) =>
        name.endsWith(".docx"),
      ) || "missing",
    )
  : "";
test("review the user's actual Word table layout", async ({ page }) => {
  test.skip(!source || !existsSync(source), "Local project manuscript");
  await page.goto("/#/tools/word");
  await page.getByLabel("导入 Word 文档").setInputFiles(source);
  await page
    .getByRole("button", { name: "匹配并确认组别", exact: true })
    .click();
  await expect(
    page.getByText("已确认组别", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: /表格匹配/ }).click();
  const row = page
    .locator(".word-fields-table tbody tr")
    .filter({ has: page.getByRole("button", { name: /编辑规则：性别/ }) })
    .first();
  await expect(row).toBeVisible();
  await expect(row.locator(".word-rule-lines > span")).toHaveCount(2);
  await page.screenshot({ path: "test-results/word-compact-real-header.png" });
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/word-compact-real-rules.png" });
});
