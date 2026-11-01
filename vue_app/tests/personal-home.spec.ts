import { test, expect } from "@playwright/test";

test("personal welcome uses app icon, real weather fields, city switching and local-time messages", async ({
  page,
}) => {
  await page.clock.install({ time: new Date(2026, 10, 2, 12, 0) });
  let city = {
    name: "焦作市",
    label: "河南省 · 焦作市",
    latitude: 35.23925,
    longitude: 113.23914,
  };
  await page.route("**/api/bridge", async (route) => {
    const request = route.request().postDataJSON();
    if (request.method === "weather.current")
      return route.fulfill({
        json: {
          ok: true,
          result: {
            configured: true,
            location: city,
            description: "晴",
            emoji: "☀️",
            temperature: 17.5,
            updated_at: new Date().toISOString(),
            stale: false,
          },
        },
      });
    if (request.method === "weather.search")
      return route.fulfill({
        json: {
          ok: true,
          result: [
            {
              name: "测试城市",
              label: "测试省 · 测试城市",
              latitude: 30,
              longitude: 110,
            },
          ],
        },
      });
    if (request.method === "weather.choose") {
      city = request.params.location;
      return route.fulfill({ json: { ok: true, result: city } });
    }
    return route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "丁丁宝宝，欢迎回来 😘❤️", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "该补充能量了，宝宝记得吃饭呀 🍚❤️",
      exact: true,
    }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator("img.brand-icon")
        .evaluate((img: HTMLImageElement) => img.naturalWidth),
    )
    .toBeGreaterThan(0);
  await expect(
    page.getByRole("button", { name: "天气与城市设置", exact: true }),
  ).toContainText("焦作市");
  await expect(
    page.getByRole("button", { name: "天气与城市设置", exact: true }),
  ).toContainText("17.5°C");
  await page
    .getByRole("button", { name: "天气与城市设置", exact: true })
    .click();
  await page.getByLabel("天气城市名称").fill("测试城市");
  await page.getByRole("button", { name: "搜索城市", exact: true }).click();
  await page
    .getByRole("button", { name: "测试省 · 测试城市", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "天气与城市设置", exact: true }),
  ).toContainText("测试城市");
  await page.clock.setSystemTime(new Date(2026, 10, 2, 1, 0));
  await page.clock.runFor(30_000);
  await expect(
    page.getByRole("heading", {
      name: "该睡觉了宝宝，明天再加油吧 😘🌙",
      exact: true,
    }),
  ).toBeVisible();
  await page.clock.setSystemTime(new Date(2026, 10, 2, 10, 0));
  await page.clock.runFor(30_000);
  await expect(
    page.getByRole("heading", { name: "加油宝宝 💪❤️", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/v301-personal-home.png",
    fullPage: true,
  });
});

test("time messages handle the 1am and meal boundaries", async ({ page }) => {
  await page.goto("/");
  const messages = await page.evaluate(async () => {
    const { homeMessage } = await import("/src/lib/home.ts");
    return [
      [0, 59],
      [1, 0],
      [6, 59],
      [7, 0],
      [9, 0],
      [11, 29],
      [11, 30],
      [13, 29],
      [13, 30],
    ].map(([h, m]) => homeMessage(new Date(2026, 10, 2, h, m)));
  });
  expect(messages[0]).toContain("休息");
  expect(messages[1]).toContain("睡觉");
  expect(messages[2]).toContain("睡觉");
  expect(messages[3]).toContain("能量");
  expect(messages[4]).toContain("加油");
  expect(messages[5]).toContain("加油");
  expect(messages[6]).toContain("能量");
  expect(messages[7]).toContain("能量");
  expect(messages[8]).toContain("加油");
});
