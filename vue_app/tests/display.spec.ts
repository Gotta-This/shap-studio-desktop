import { test, expect } from "@playwright/test";

test("short sidebar scrolls through every tool to settings and updates", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 520 });
  await page.goto("/");
  const sidebar = page.locator(".sidebar");
  expect(
    await sidebar.evaluate((e) => e.scrollHeight > e.clientHeight),
  ).toBeTruthy();
  await sidebar.locator('a[href="#/tools/prediction"]').click();
  await expect(page).toHaveURL(/prediction/);
  await sidebar.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "界面显示" })).toBeVisible();
  await sidebar
    .getByRole("link", { name: "检查更新", exact: true })
    .scrollIntoViewIfNeeded();
  const box = await sidebar
    .getByRole("link", { name: "检查更新", exact: true })
    .boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(520);
});
for (const scale of [80, 125]) {
  test(`global ${scale}% zoom survives reload and keeps popups and inputs usable`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 680 });
    await page.goto("/#/settings");
    await page.getByRole("combobox", { name: "界面缩放", exact: true }).click();
    await page.getByRole("option", { name: `${scale}%`, exact: true }).click();
    await expect
      .poll(() =>
        page.evaluate(() =>
          localStorage.getItem("research-studio.display-scale"),
        ),
      )
      .toBe(String(scale));
    await page.reload();
    await expect(
      page.getByRole("combobox", { name: "界面缩放", exact: true }),
    ).toContainText(`${scale}%`);
    const before = await page.locator(".main-content").boundingBox();
    await page
      .getByRole("button", { name: "搜索任务与文件", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page
      .getByRole("textbox", { name: "全局搜索", exact: true })
      .fill("缩放测试");
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(1101);
    expect(box!.y + box!.height).toBeLessThanOrEqual(681);
    expect(
      Math.abs(
        (await page.locator(".main-content").boundingBox())!.width -
          before!.width,
      ),
    ).toBeLessThan(1);
    await page.keyboard.press("Escape");
    await page.getByRole("combobox", { name: "界面缩放", exact: true }).click();
    const popup = page.getByRole("listbox");
    await expect(popup).toBeVisible();
    const popbox = await popup.boundingBox();
    expect(popbox!.x).toBeGreaterThanOrEqual(0);
    expect(popbox!.x + popbox!.width).toBeLessThanOrEqual(1101);
    expect(popbox!.y + popbox!.height).toBeLessThanOrEqual(681);
    await page
      .getByRole("option", { name: "100%（默认）", exact: true })
      .click();
    await expect
      .poll(() =>
        page.evaluate(() => getComputedStyle(document.documentElement).zoom),
      )
      .toBe("1");
    const side = await page.locator(".sidebar").boundingBox();
    expect(side!.y + side!.height).toBeLessThanOrEqual(681);
  });
}
test("invalid saved zoom falls back to 100% and reset is saved", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("research-studio.display-scale", "0.01"),
  );
  await page.goto("/#/settings");
  await expect(
    page.getByRole("combobox", { name: "界面缩放", exact: true }),
  ).toContainText("100%");
  await page.getByRole("combobox", { name: "界面缩放", exact: true }).click();
  await page.getByRole("option", { name: "70%", exact: true }).click();
  await page.getByRole("button", { name: "恢复 100%", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("research-studio.display-scale"),
      ),
    )
    .toBe("100");
});
