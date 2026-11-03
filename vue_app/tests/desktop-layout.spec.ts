import { test, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

const id = (n: number) => String(n).padStart(32, "0");
const record = (n: number, pinned = false, label = `备份 ${n}`) => ({
  id: id(n),
  label,
  created_at: "2026-11-03T10:00:00+08:00",
  protected: pinned,
  reason: "manual",
  icon_count: 12,
  display: { width: 1920, height: 1080, dpi: 96 },
});
async function windows(page: Page, dueNow = false) {
  const store = {
    rows: [record(1, true), record(2), record(3), record(4)],
    settings: {
      enabled: true,
      interval_minutes: 1,
      keep_recent: 20,
      last_automatic_at: "",
      next_due_at: Date.now() / 1000 + (dueNow ? -1 : 60),
      last_error: "",
    },
    automatic: 0,
    restoreCalls: 0,
    failPreview: false,
    unmatched: 0,
    needsMove: 2,
    lastBackup: null as any,
  };
  await page.route("**/api/bridge", async (route) => {
    const { method, params: p } = route.request().postDataJSON();
    if (!method.startsWith("desktop.layout.")) {
      await route.fallback();
      return;
    }
    let result: any;
    switch (method.split(".").pop()) {
      case "info":
        result = {
          supported: true,
          backups: store.rows,
          directory: "C:\\Users\\test\\Documents\\.research\\desktop-layouts",
          keep_recent: store.settings.keep_recent,
          settings: store.settings,
        };
        break;
      case "tick": {
        const now = await page.evaluate(() => Date.now() / 1000);
        let created = null;
        if (store.settings.enabled && now >= store.settings.next_due_at) {
          created = id(100 + ++store.automatic);
          store.rows.unshift({
            ...record(100 + store.automatic),
            reason: "automatic",
          });
          store.settings.next_due_at =
            now + store.settings.interval_minutes * 60;
          store.settings.last_automatic_at = new Date(now * 1000).toISOString();
        }
        result = { supported: true, created, ...store.settings };
        break;
      }
      case "backup":
        store.lastBackup = p;
        store.rows.unshift(record(20, p.protected, p.label));
        result = store.rows[0];
        break;
      case "protect":
        store.rows.find((r) => r.id === p.id)!.protected = p.protected;
        result = {};
        break;
      case "delete":
        store.rows = store.rows.filter((r) => r.id !== p.id);
        result = {};
        break;
      case "preview":
        if (store.failPreview) {
          await route.fulfill({
            json: {
              ok: false,
              error: "当前桌面没有足够的空位置放置新增图标，未移动任何图标。",
            },
          });
          return;
        }
        result = {
          restored_count: 2,
          new_count: 1,
          missing_count: 1,
          needs_move_count: store.needsMove,
          display_changed: false,
          fingerprint: "confirmed-layout",
        };
        break;
      case "restore":
        expect(p.fingerprint).toBe("confirmed-layout");
        store.restoreCalls++;
        result = {
          unmatched_positions: store.unmatched,
          restored_count: 2,
          new_count: 1,
          missing_count: 1,
          needs_move_count: store.needsMove,
          diagnostic_id: "diagnostic-operation-123",
          diagnostic_saved: true,
        };
        break;
      case "diagnostics":
        result = {
          name: "desktop-layout-diagnostics-test.json",
          content: JSON.stringify({
            schema: 1,
            events: [
              { event: "native.position.result", hresult: "0x00000000" },
            ],
          }),
        };
        break;
      case "settings": {
        Object.assign(store.settings, p);
        const normals = store.rows
          .filter((r) => !r.protected)
          .slice(0, p.keep_recent);
        const before = store.rows.length;
        store.rows = store.rows.filter(
          (r) => r.protected || normals.includes(r),
        );
        result = {
          settings: store.settings,
          removed: before - store.rows.length,
        };
        break;
      }
      default:
        throw new Error(method);
    }
    await route.fulfill({ json: { ok: true, result } });
  });
  return store;
}

test("Mac clearly disables desktop operations and backend refuses capture", async ({
  page,
  request,
}) => {
  await page.goto("/#/tools/desktop-layout");
  await expect(
    page.getByRole("heading", { name: "非windows电脑无法使用", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "备份当前排列", exact: true }),
  ).toHaveCount(0);
  const response = await request.post("/api/bridge", {
    data: { method: "desktop.layout.backup", params: {} },
  });
  expect((await response.json()).error).toContain("非windows电脑无法使用");
});

test("Windows backup protection, merge preview, restore and deletion", async ({
  page,
}) => {
  const store = await windows(page);
  await page.setViewportSize({ width: 1024, height: 650 });
  await page.goto("/#/tools/desktop-layout");
  await page.getByRole("textbox", { name: "备份名称" }).fill("常用工作桌面");
  await page.getByRole("checkbox", { name: "永久保留此备份" }).check();
  await page.getByRole("button", { name: "备份当前排列", exact: true }).click();
  const remove = page.getByRole("button", {
    name: "删除备份 常用工作桌面",
    exact: true,
  });
  await expect(remove).toBeDisabled();
  expect(store.lastBackup).toEqual({ label: "常用工作桌面", protected: true });
  await page
    .getByRole("button", { name: "恢复备份 常用工作桌面", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "恢复 2 个已有图标；1 个新增图标将放入空网格",
  );
  expect(store.restoreCalls).toBe(0);
  await page.getByRole("button", { name: "确认恢复排列", exact: true }).click();
  await expect.poll(() => store.restoreCalls).toBe(1);
  await page
    .getByRole("button", { name: "取消永久保留 常用工作桌面", exact: true })
    .click();
  await page
    .getByRole("button", { name: "确认取消永久保留", exact: true })
    .click();
  await expect(remove).toBeEnabled();
  await remove.click();
  await page.getByRole("button", { name: "确认删除备份", exact: true }).click();
  await expect(remove).toHaveCount(0);
});

test("insufficient desktop space blocks restore with a visible explanation", async ({
  page,
}) => {
  const store = await windows(page);
  store.failPreview = true;
  await page.goto("/#/tools/desktop-layout");
  await page
    .getByRole("button", { name: "恢复备份 备份 1", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("没有足够的空位置");
  expect(store.restoreCalls).toBe(0);
});

test("global timer runs on other pages; retention excludes permanent backups; disable stops capture", async ({
  page,
}) => {
  const clock = new Date();
  await page.clock.install({ time: clock });
  const store = await windows(page, true);
  await page.goto("/#/todos");
  await expect.poll(() => store.automatic).toBe(1);
  await page.clock.fastForward(61000);
  await expect.poll(() => store.automatic).toBe(2);
  await page.goto("/#/tools/desktop-layout");
  await page.getByRole("spinbutton", { name: "备份频率（分钟）" }).fill("2");
  await page.getByRole("spinbutton", { name: "普通备份保留份数" }).fill("2");
  await page.getByRole("button", { name: "保存备份设置", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("永久备份会全部保留");
  await page
    .getByRole("button", { name: "确认保存并清理", exact: true })
    .click();
  await expect.poll(() => store.rows.length).toBe(3);
  expect(store.rows.some((r) => r.id === id(1) && r.protected)).toBe(true);
  expect(store.settings.interval_minutes).toBe(2);
  await page.getByRole("checkbox", { name: "启用自动备份" }).uncheck();
  await page.getByRole("button", { name: "保存备份设置", exact: true }).click();
  await expect.poll(() => store.settings.enabled).toBe(false);
  const count = store.automatic;
  await page.clock.fastForward(180000);
  expect(store.automatic).toBe(count);
});

test("temporary startup failure retries the automatic backup", async ({
  page,
}) => {
  await page.clock.install();
  const store = await windows(page, true);
  let failed = false;
  await page.route("**/api/bridge", async (route) => {
    if (
      !failed &&
      route.request().postDataJSON().method === "desktop.layout.tick"
    ) {
      failed = true;
      await route.fulfill({ json: { ok: false, error: "Python 正在启动" } });
    } else await route.fallback();
  });
  await page.goto("/#/todos");
  await expect.poll(() => failed).toBe(true);
  expect(store.automatic).toBe(0);
  await page.clock.fastForward(31000);
  await expect.poll(() => store.automatic).toBe(1);
});

test("restore failure stays visible and diagnostics can be downloaded", async ({
  page,
}) => {
  const store = await windows(page);
  store.unmatched = 2;
  await page.goto("/#/tools/desktop-layout");
  await page
    .getByRole("button", { name: "恢复备份 备份 1", exact: true })
    .click();
  await page.getByRole("button", { name: "确认恢复排列", exact: true }).click();
  const status = page.locator(".layout-backup-page [role=status]");
  await expect(status).toContainText("2 个图标未按预期落位");
  await expect(status).toContainText("诊断编号");
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出诊断日志", exact: true }).click();
  const exported = await pending;
  const value = JSON.parse(await readFile((await exported.path())!, "utf8"));
  expect(value.events[0].hresult).toBe("0x00000000");
  await expect(status).toContainText("未按预期落位");
});

test("unchanged layout is explained before and after restore", async ({
  page,
}) => {
  const store = await windows(page);
  store.needsMove = 0;
  await page.goto("/#/tools/desktop-layout");
  await page
    .getByRole("button", { name: "恢复备份 备份 1", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("没有需要移动的图标");
  await page.getByRole("button", { name: "确认恢复排列", exact: true }).click();
  await expect(page.locator(".layout-backup-page [role=status]")).toContainText(
    "所选备份与当前排列一致",
  );
});
