import { test, expect } from "@playwright/test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

test("update check retries, downloads and opens verified package through host adapter", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const host = window as any;
    host.__opened = [];
    host.__TAURI_INTERNALS__ = {
      metadata: {
        currentWindow: { label: "main" },
        currentWebview: { label: "main", windowLabel: "main" },
      },
      transformCallback: () => 1,
      unregisterCallback: () => {},
      invoke: async (cmd: string, args: any) => {
        if (cmd === "python_request") {
          return (
            await fetch("/api/bridge", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(args.request),
            })
          ).json();
        }
        if (cmd === "plugin:opener|open_path") host.__opened.push(args.path);
        return 1;
      },
    };
  });
  let fail = true;
  await page.route("**/api/bridge", async (route) => {
    const request = route.request().postDataJSON();
    if (request.method === "updates.check") {
      await route.fulfill({
        json: fail
          ? { ok: false, error: "网络不可用" }
          : {
              ok: true,
              result: {
                newer: true,
                version: "3.0.1",
                asset: { name: "installer" },
              },
            },
      });
    } else if (request.method === "updates.download") {
      await route.fulfill({
        json: {
          ok: true,
          result: { path: "/tmp/verified-update.zip", version: "3.0.1" },
        },
      });
    } else await route.continue();
  });
  await page.goto("/#/settings");
  await expect(page.getByRole("alert")).toContainText("网络不可用");
  fail = false;
  await page.getByRole("button", { name: "检查更新", exact: true }).click();
  await expect(page.getByText("发现新版本 V3.0.1")).toBeVisible();
  await page
    .getByRole("button", { name: "下载并校验更新", exact: true })
    .click();
  await page.getByRole("button", { name: "打开更新包", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => (window as any).__opened))
    .toEqual(["/tmp/verified-update.zip"]);
});

test("Qt personal todo migration uses real backend and remains idempotent", async ({
  page,
}) => {
  const folder = mkdtempSync(join(tmpdir(), "v3-qt-migration-"));
  const text = "从 Qt 迁移的个人工作 " + Date.now();
  writeFileSync(
    join(folder, "todos.json"),
    JSON.stringify({
      version: 1,
      tasks: [
        {
          id: text,
          name: text,
          priority: "high",
          due_date: "2028-02-29",
          completed: false,
          deleted: false,
        },
      ],
    }),
  );
  try {
    await page.goto("/#/settings");
    await page.getByLabel("迁移 Qt 版本的数据").fill(folder);
    await page
      .getByRole("button", { name: "迁移 Qt 数据", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("已迁移 1 条");
    await page
      .getByRole("button", { name: "迁移 Qt 数据", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("已迁移 0 条");
    await page.getByRole("link", { name: /待办事项/ }).click();
    await expect(page.getByText(text, { exact: true })).toBeVisible();
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
});
