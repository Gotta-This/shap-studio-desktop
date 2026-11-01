import { test, expect } from "@playwright/test";
import { mkdtempSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
test("desktop export uses the native save adapter and writes a complete file", async ({
  page,
}) => {
  const root = mkdtempSync(join(tmpdir(), "v3-native-save-")),
    path = join(root, "模拟数据.csv");
  try {
    // Replace only the desktop host adapter: no system dialog or OS input.
    // Python requests still reach the actual local bridge and filesystem.
    await page.addInitScript(
      ({ path }) => {
        const host = window as any;
        let callback = 0;
        host.__nativeCalls = [];
        host.__TAURI_INTERNALS__ = {
          metadata: {
            currentWindow: { label: "main" },
            currentWebview: { label: "main", windowLabel: "main" },
          },
          transformCallback: () => ++callback,
          unregisterCallback: () => {},
          invoke: async (command: string, args: any) => {
            host.__nativeCalls.push({ command, args });
            if (command === "python_request") {
              const response = await fetch("/api/bridge", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(args.request),
              });
              return response.json();
            }
            if (command === "plugin:dialog|save") return path;
            return 1;
          },
        };
      },
      { path },
    );
    await page.goto("/#/tools/category");
    await page
      .getByRole("button", { name: "生成随机数列", exact: true })
      .click();
    await expect(page.getByLabel("全部生成数值")).not.toHaveValue("");
    await page.getByRole("button", { name: "导出 CSV", exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "已保存到" }),
    ).toBeVisible({ timeout: 30000 });
    expect(existsSync(path)).toBe(true);
    expect(readFileSync(path, "utf8").trim().split(/\r?\n/)).toHaveLength(122);
    const calls = await page.evaluate(() => (window as any).__nativeCalls);
    expect(calls.some((c: any) => c.command === "plugin:dialog|save")).toBe(
      true,
    );
    expect(
      calls.some(
        (c: any) =>
          c.command === "python_request" &&
          c.args.request.method === "exports.save",
      ),
    ).toBe(true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
