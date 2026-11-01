import { test, expect } from "@playwright/test";

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
                version: "3.0.3",
                asset: { name: "installer" },
              },
            },
      });
    } else if (request.method === "updates.download") {
      await route.fulfill({
        json: {
          ok: true,
          result: { path: "/tmp/verified-update.zip", version: "3.0.3" },
        },
      });
    } else await route.continue();
  });
  await page.goto("/#/settings");
  await expect(page.getByRole("alert")).toContainText("网络不可用");
  fail = false;
  await page.getByRole("button", { name: "检查更新", exact: true }).click();
  await expect(page.getByText("发现新版本 V3.0.3")).toBeVisible();
  await page
    .getByRole("button", { name: "下载并校验更新", exact: true })
    .click();
  await page.getByRole("button", { name: "打开更新包", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => (window as any).__opened))
    .toEqual(["/tmp/verified-update.zip"]);
});

test("settings shows persistent data directory and hides Qt migration", async ({
  page,
}) => {
  await page.goto("/#/settings");
  await expect(page.getByText("应用数据目录", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "打开应用数据目录", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "迁移 Qt 数据", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("替换或重新安装应用不会清除这些数据", { exact: false }),
  ).toBeVisible();
});
