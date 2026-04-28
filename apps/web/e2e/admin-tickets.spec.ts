import { expect, test } from "@playwright/test";

test("admin-tickets: nav visible and ticket cards render", async ({ page }) => {
  // login as admin
  await page.goto("/login");
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[autocomplete="current-password"]').fill("admin123");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "聊天分析" })).toBeVisible();

  // admin menu item is visible
  await expect(page.getByRole("link", { name: "AI 异常工单" })).toBeVisible();

  // navigate to tickets page
  await page.getByRole("link", { name: "AI 异常工单" }).click();
  await expect(page.getByRole("heading", { name: "AI 异常工单" })).toBeVisible();

  // at least one ticket card with an error block renders
  const cards = page.locator(".card");
  await expect(cards.first()).toBeVisible();
  await expect(page.locator("pre.code-block").first()).toBeVisible();
});
