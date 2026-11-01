import { test, expect } from "@playwright/test";
import {
  readdirSync,
  existsSync,
  readFileSync,
  mkdirSync,
  appendFileSync,
} from "node:fs";
import { resolve, join, relative } from "node:path";
const root = resolve("../word"),
  evidence = resolve(".v3-data/audit-qt-corpus");
function documents(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? documents(join(dir, e.name))
      : /\.docx?$/i.test(e.name)
        ? [join(dir, e.name)]
        : [],
  );
}
const files =
  existsSync(root) && existsSync(join(evidence, "comparison.json"))
    ? documents(root).sort()
    : [];
const reportFile = join(evidence, "comparison.json");
const reference: any[] = existsSync(reportFile)
  ? JSON.parse(readFileSync(reportFile, "utf8"))
  : [];
if (!files.length)
  test("project Word corpus is local-only", () =>
    test.skip(
      true,
      "Run scripts/audit-qt-corpus.py first with the local Word corpus",
    ));
for (const [index, path] of files.entries())
  test(`real Word ${index + 1}: ${relative(root, path)}`, async ({ page }) => {
    test.setTimeout(90000);
    page.on("websocket", (socket) =>
      socket.on("framereceived", (frame) => {
        try {
          const message = JSON.parse(String(frame.payload));
          if (message.type === "full-reload")
            appendFileSync(
              "/private/tmp/dbq-v3-reload-diagnostic.log",
              JSON.stringify(message) + "\n",
            );
        } catch {}
      }),
    );
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/#/tools/word");
    const scanResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/bridge") &&
        r.request().postDataJSON()?.method === "tool.word.scan",
    );
    await page.getByLabel("导入 Word 文档").setInputFiles(path);
    const envelope = await (await scanResponse).json();
    expect(envelope.ok, envelope.error).toBe(true);
    const scanned = envelope.result.scan;
    await expect(
      page.getByRole("button", { name: "查看原表与识别草稿" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "查看原表与识别草稿" }).click();
    await expect(page.getByRole("dialog")).toContainText("Word 原表与识别草稿");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "完整正文", exact: true })
      .click();
    if (scanned.prose_text.trim())
      await expect(page.locator("pre.source-prose")).toContainText(
        scanned.prose_text.trim().slice(0, 15),
      );
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const ref = reference.find(
      (r) => r.file === relative(root, path) && r.mode === "defaults",
    );
    const selected: string[] =
      ref?.manually_selected_groups || scanned.candidates;
    if (!scanned.has_ungrouped || selected.length) {
      // Exercise the same manual removal of unmatched candidates as in Qt.
      if (selected.join("|") !== scanned.candidates.join("|")) {
        const removals = page.getByRole("button", { name: /删除组别/ });
        while (await removals.count()) await removals.last().click();
        for (const name of selected) {
          await page
            .getByRole("button", { name: "添加组别", exact: true })
            .click();
          await page
            .getByLabel(
              "匹配组别 " +
                (await page.getByRole("textbox", { name: /匹配组别/ }).count()),
              { exact: true },
            )
            .fill(name);
        }
      }
      if (selected.length) {
        await page
          .getByRole("button", { name: "核对组别匹配", exact: true })
          .click();
        await expect(
          page.getByText("张表、", { exact: false }).first(),
        ).toBeVisible();
      }
    } else if (!scanned.ungrouped_n) {
      await expect(page.getByLabel("无分组生成例数")).toHaveValue("");
      await page.getByLabel("无分组生成例数").fill("20");
    }
    const appliedResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/bridge") &&
        r.request().postDataJSON()?.method === "tool.word.apply",
    );
    await page
      .getByRole("button", { name: "匹配并确认组别", exact: true })
      .click();
    const applied = await (await appliedResponse).json();
    if (ref?.expected_block || (!selected.length && !scanned.has_ungrouped)) {
      expect(applied.ok).toBe(false);
      await expect(page.getByRole("alert")).toBeVisible();
      expect(errors).toEqual([]);
      return;
    }
    expect(applied.ok, applied.error).toBe(true);
    await page.getByRole("tab", { name: /表格匹配/ }).click();
    const fieldCount = ["typed_fields", "indicators", "categoricals"].reduce(
      (n, k) => n + (applied.result.config[k]?.length || 0),
      0,
    );
    if (fieldCount)
      await expect(
        page
          .getByRole("columnheader", { name: "Word 原文", exact: true })
          .first(),
      ).toBeVisible();
    await page.getByRole("tab", { name: /全部字段以及来源/ }).click();
    await expect(
      page.getByRole("heading", { name: "全部字段以及来源", exact: true }),
    ).toBeVisible();
    await page.getByRole("tab", { name: /生成与导出/ }).click();
    await page
      .getByRole("button", { name: "生成模拟数据", exact: true })
      .click();
    if (ref?.qt_validation) {
      await expect(page.getByRole("alert")).toBeVisible({ timeout: 30000 });
      await expect(
        page.getByRole("button", { name: "导出完整 Excel" }),
      ).toHaveCount(0);
    } else {
      await expect(
        page.getByRole("button", { name: "导出完整 Excel" }),
      ).toBeVisible({ timeout: 60000 });
      if (ref?.generated_rows)
        await expect(
          page.getByText("共 " + ref.generated_rows + " 行", { exact: false }),
        ).toBeVisible();
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name: "导出完整 Excel" }).click();
      mkdirSync(evidence, { recursive: true });
      await (
        await download
      ).saveAs(join(evidence, `browser-corpus-${index + 1}.xlsx`));
    }
    if (index === 0 || index === files.length - 1)
      await page.screenshot({
        path: join(evidence, `browser-corpus-${index + 1}.png`),
        fullPage: true,
      });
    expect(errors).toEqual([]);
  });

const proseReference = reference.find(
  (r) =>
    r.mode === "source-options" &&
    r.generated_rows &&
    !r.qt_validation &&
    !r.expected_block,
);
if (proseReference)
  test("real Word with explicit original counts, outcomes and editable prose", async ({
    page,
  }) => {
    test.setTimeout(90000);
    await page.goto("/#/tools/word");
    await page
      .getByRole("checkbox", { name: "采用 Word 中的例数", exact: true })
      .check();
    await page
      .getByRole("checkbox", { name: "采用正文一般资料", exact: true })
      .check();
    await page.getByRole("checkbox", { name: /采用 Word 表中的有效/ }).check();
    await page
      .getByLabel("导入 Word 文档")
      .setInputFiles(join(root, proseReference.file));
    await expect(
      page.getByRole("button", { name: "查看原表与识别草稿" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "匹配并确认组别", exact: true })
      .click();
    await page.getByRole("tab", { name: /文字匹配/ }).click();
    await expect(page.getByLabel("一般资料原文")).not.toHaveValue("");
    await page.getByRole("tab", { name: /生成与导出/ }).click();
    await page
      .getByRole("button", { name: "生成模拟数据", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "导出完整 Excel" }),
    ).toBeVisible({ timeout: 60000 });
    await expect(
      page.getByText("共 " + proseReference.generated_rows + " 行", {
        exact: false,
      }),
    ).toBeVisible();
  });
