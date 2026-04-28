import { expect, test } from "@playwright/test";

test("login page shows TalkBI", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "TalkBI" })).toBeVisible();
});
