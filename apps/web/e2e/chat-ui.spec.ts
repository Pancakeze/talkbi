import { expect, test } from "@playwright/test";

test("chat page UI: theme scope empty + error guide when sending without themes", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[autocomplete="current-password"]').fill("admin123");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page.getByTestId("chat-page")).toBeVisible();
  await expect(page.getByTestId("theme-scope")).toBeVisible();

  // Theme libraries are empty on fresh E2E DB; scope dropdown should show empty state.
  await page.getByTestId("theme-scope-trigger").click();
  await expect(page.getByTestId("theme-scope-search")).toBeVisible();
  await expect(page.getByText("暂无主题库，请先在「主题库管理」中创建")).toBeVisible();

  // With no themes selected, sending should produce the guided error bubble.
  await page.getByTestId("chat-input").fill("随便问点什么");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-error-guide")).toBeVisible();

  // Right panel should remain in empty state.
  await expect(page.getByTestId("chart-empty")).toBeVisible();
});

