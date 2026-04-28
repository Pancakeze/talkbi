import { expect, test } from "@playwright/test";

function csvBuffer() {
  const csv = [
    "district_name,congestion_index,accident_count",
    "A区,1.2,10",
    "B区,3.4,20"
  ].join("\n");
  return Buffer.from(csv, "utf-8");
}

test("MVP flow: upload -> theme -> chat -> save chart -> dashboard layout", async ({ page }) => {
  // login
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "TalkBI" })).toBeVisible();
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[autocomplete="current-password"]').fill("admin123");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "聊天分析" })).toBeVisible();

  // upload CSV as "excel" datasource
  await page.getByRole("link", { name: "数据源管理" }).click();
  await expect(page.getByRole("heading", { name: "数据源管理" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "traffic.csv",
    mimeType: "text/csv",
    buffer: csvBuffer()
  });
  await expect(page.getByText("Excel 已上传并解析元数据")).toBeVisible();
  await expect(page.locator("li.card").filter({ hasText: "traffic.csv — excel — active" }).first()).toBeVisible();

  // create theme bound to that datasource
  await page.getByRole("link", { name: "主题库管理" }).click();
  await expect(page.getByRole("heading", { name: "主题库管理" })).toBeVisible();

  const createThemeForm = page.locator("form").filter({ has: page.getByRole("button", { name: "创建" }) });
  await createThemeForm.locator('input[class~="input"]').first().fill("E2E 主题库");
  const dsSelect = createThemeForm.locator("select").first();
  await expect(dsSelect.locator("option")).toHaveCount(2);
  await dsSelect.selectOption({ index: 1 });
  await createThemeForm.getByRole("button", { name: "创建" }).click();
  await expect(page.getByText("主题库已创建")).toBeVisible();
  await page.getByRole("button", { name: "E2E 主题库" }).click();

  // add a visible field (this is enough for backend mock SQL generation)
  const addFieldForm = page.locator("form").filter({ has: page.getByRole("button", { name: "添加字段" }) });
  await addFieldForm.locator('input[class~="input"]').nth(1).fill("congestion_index");
  await addFieldForm.locator('input[class~="input"]').nth(2).fill("拥堵指数");
  await page.getByRole("button", { name: "添加字段" }).click();
  await expect(page.getByText("字段已添加")).toBeVisible();
  await expect(page.getByText(/\.congestion_index → 拥堵指数/)).toBeVisible();

  // chat query produces chart
  await page.getByRole("link", { name: "聊天分析" }).click();
  await expect(page.getByRole("heading", { name: "聊天分析" })).toBeVisible();
  await page.getByTestId("chat-input").fill("查看各区指标");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("chat-loading")).toBeVisible();
  await expect(page.getByTestId("chat-loading")).toBeHidden();
  await expect(page.getByTestId("chat-sql")).toContainText("SELECT");

  // save to chart library
  await page.getByTestId("chat-save").click();
  await expect(page.getByTestId("chat-save")).toContainText("已保存");

  // chart appears in library
  await page.getByRole("link", { name: "个人图表库" }).click();
  await expect(page.getByRole("heading", { name: "个人图表库" })).toBeVisible();
  await expect(page.locator(".drag-item")).toHaveCount(1);

  // add chart to dashboard and persist layout
  await page.getByRole("link", { name: "仪表盘" }).click();
  await expect(page.getByRole("heading", { name: "仪表盘" })).toBeVisible();
  await page.getByRole("combobox").selectOption({ index: 1 });
  await page.getByRole("button", { name: "添加到仪表盘" }).click();
  await page.getByRole("button", { name: "保存布局到服务器" }).click();
  await expect(page.getByText("布局已保存")).toBeVisible();
});

