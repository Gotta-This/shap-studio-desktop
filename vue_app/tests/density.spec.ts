import { test, expect } from "@playwright/test";
const routes = [
  "/",
  "/workspace",
  "/todos",
  "/inbox",
  "/tools/category",
  "/tools/numeric",
  "/tools/word",
  "/tools/shap",
  "/settings",
];
test("all pages use compact headings and explicit row actions", async ({
  page,
  request,
}) => {
  const text = "界面密度验收-" + Date.now();
  const response = await request.post("/api/bridge", {
    data: { method: "todo.save", params: { text } },
  });
  const id = (await response.json()).result;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    for (const route of routes) {
      await page.goto("/#" + route);
      await expect(page.locator(".page-heading")).toBeVisible();
      if (route === "/tools/shap" || route === "/tools/word")
        await expect(
          page.locator(".scientific-section h2").first(),
        ).toBeVisible();
      const metrics = await page
        .locator(".page-heading")
        .evaluate((node) => ({
          font: getComputedStyle(node.querySelector("h1")!).fontSize,
          margin: parseFloat(getComputedStyle(node).marginBottom),
          topbar: document.querySelector(".topbar")!.getBoundingClientRect()
            .height,
        }));
      expect(metrics.font).toBe("22px");
      expect(metrics.margin).toBeLessThanOrEqual(16);
      expect(metrics.topbar).toBe(48);
      await expect(
        page.locator(
          'button[data-variant="ghost"], button[data-variant="link"]',
        ),
      ).toHaveCount(0);
      await page.screenshot({
        path:
          "test-results/compact-" +
          (route.replaceAll("/", "-") || "home") +
          ".png",
      });
    }
    await page.goto("/#/todos");
    const button = page.getByRole("button", { name: text, exact: true });
    await expect(button).toBeVisible();
    const row = button.locator("xpath=ancestor::tr");
    expect((await row.boundingBox())!.height).toBeLessThan(76);
    expect(
      await button.evaluate((node) => getComputedStyle(node).borderTopWidth),
    ).toBe("1px");
    await button.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await request.post("/api/bridge", {
      data: { method: "todo.save", params: { id, deleted: true } },
    });
  }
});
