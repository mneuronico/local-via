import { expect, test } from "@playwright/test";

test("deployed UI connects through the HTTPS tunnel", async ({ page }) => {
  const url = process.env.REMOTE_WORKER_URL;
  const token = process.env.REMOTE_WORKER_TOKEN;
  test.skip(!url || !token, "REMOTE_WORKER_URL and REMOTE_WORKER_TOKEN are required");

  const browserErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.addInitScript((config) => {
    localStorage.setItem("local-via-worker", JSON.stringify(config));
  }, { url, token });

  await page.goto("/");
  await expect(page.getByRole("button", { name: /aula-pc-01/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("NVIDIA GeForce RTX 2060").first()).toBeVisible();
  expect(browserErrors).toEqual([]);
});
