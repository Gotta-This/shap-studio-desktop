import { test, expect } from "@playwright/test";

test("collapsed navigation stays compact across desktop and narrow breakpoints", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "收起侧栏", exact: true }).click();
  for (const width of [1100, 950, 900, 800, 701]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(async () => (await page.locator(".sidebar").boundingBox())!.width)
      .toBe(70);
    await expect
      .poll(async () => (await page.locator(".shell-body").boundingBox())!.x)
      .toBe(70);
  }
  await page.screenshot({
    path: "test-results/v301-narrow-sidebar.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "展开侧栏", exact: true }).click();
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())!.width)
    .toBe(190);
  await page.setViewportSize({ width: 640, height: 900 });
  await expect(page.locator(".sidebar-toggle")).toBeHidden();
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())!.width)
    .toBe(64);
  await page.setViewportSize({ width: 1100, height: 900 });
  await expect
    .poll(async () => (await page.locator(".sidebar").boundingBox())!.width)
    .toBe(224);
});

test("native host startup errors are shown and allow retry, instead of a preparing toast", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const host = window as any;
    host.__TAURI_INTERNALS__ = {
      metadata: {
        currentWindow: { label: "main" },
        currentWebview: { label: "main", windowLabel: "main" },
      },
      transformCallback: () => 1,
      unregisterCallback: () => {},
      invoke: async (command: string, args: any) => {
        if (command === "python_request") {
          if (args.request.method === "tool.job.start" && !host.__retryEngine)
            throw "Python 引擎无法启动：路径不存在";
          if (args.request.method === "updates.check")
            return { ok: true, result: { current: "3.0.1", newer: false } };
          return (
            await fetch("/api/bridge", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(args.request),
            })
          ).json();
        }
        return 1;
      },
    };
  });
  await page.goto("/#/tools/numeric");
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Python 引擎无法启动：路径不存在",
  );
  await expect(
    page.getByRole("button", { name: "生成模拟数据", exact: true }),
  ).toBeEnabled();
  await page.evaluate(() => ((window as any).__retryEngine = true));
  await page.getByRole("button", { name: "生成模拟数据", exact: true }).click();
  await expect(page.getByLabel("全部生成数值")).not.toHaveValue("");
  const rows = (await page.getByLabel("全部生成数值").inputValue())
    .trim()
    .split(/\r?\n/)
    .map(Number);
  expect(rows).toHaveLength(70);
  expect(rows.reduce((n, v) => n + v, 0) / rows.length).toBeCloseTo(27.92, 1);
  await page.screenshot({
    path: "test-results/v301-numeric-generated.png",
    fullPage: true,
  });
});

test("search dialog keeps background layout stable when a classic scrollbar is removed", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1211, height: 850 });
  await page.goto("/");
  // Force a non-overlay scrollbar, matching the user's macOS setting.
  await page.addStyleTag({
    content: "::-webkit-scrollbar { width: 16px; height: 16px; }",
  });
  await page.evaluate(() => {
    document.getElementById("app")!.scrollTop = 60;
    const host = window as any;
    host.__layoutFrames = [];
    host.__recordLayout = true;
    const record = () => {
      const element = document.querySelector(".main-content")!;
      const rect = element.getBoundingClientRect();
      host.__layoutFrames.push({
        x: rect.x,
        y: rect.y,
        width: rect.width,
        padding: getComputedStyle(element).paddingLeft,
      });
      if (host.__recordLayout) requestAnimationFrame(record);
    };
    record();
  });
  const baseline = await page.locator(".main-content").boundingBox();
  for (let i = 0; i < 3; i++) {
    await page
      .getByRole("button", { name: "搜索任务与文件", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByLabel("全局搜索").fill("未找到的内容 " + i);
    await expect
      .poll(
        async () => (await page.locator(".main-content").boundingBox())!.width,
      )
      .toBe(baseline!.width);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  const frames = await page.evaluate(() => {
    const host = window as any;
    host.__recordLayout = false;
    return host.__layoutFrames;
  });
  expect(new Set(frames.map((f: any) => f.padding)).size).toBe(1);
  expect(
    Math.max(...frames.map((f: any) => f.y)) -
      Math.min(...frames.map((f: any) => f.y)),
  ).toBeLessThan(1);
  expect(
    Math.max(...frames.map((f: any) => f.width)) -
      Math.min(...frames.map((f: any) => f.width)),
  ).toBeLessThan(1);
  expect(
    Math.max(...frames.map((f: any) => f.x)) -
      Math.min(...frames.map((f: any) => f.x)),
  ).toBeLessThan(1);
});
