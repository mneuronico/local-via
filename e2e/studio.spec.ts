import { expect, test, type Page } from "@playwright/test";

const now = new Date().toISOString();
const completedJob = {
  id: "e2e-job",
  project_id: "default",
  model: "ltx2_25_22B_distilled",
  task: "text.generate",
  prompt: "Una estación de tren bajo la lluvia, cámara lenta",
  status: "succeeded",
  progress: 100,
  phase: "complete",
  created_at: now,
  updated_at: now,
  parameters: {},
  artifacts: [{
    id: "preview",
    name: "preview.svg",
    media_type: "image/svg+xml",
    size: 256,
    url: "http://worker.test/files/preview.svg",
  }],
};

async function mockWorker(page: Page) {
  let jobs: typeof completedJob[] = [];
  await page.route("http://worker.test/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/status") return route.fulfill({ json: {
      worker_id: "aula-pc-01", status: "idle", backend: "mock",
      gpu: { name: "GPU de prueba", vram_total_mb: 12288, vram_free_mb: 10240 },
      queue_depth: 0, active_job_id: null, wangp_ready: true,
    } });
    if (path === "/v1/models") return route.fulfill({ json: { models: [] } });
    if (path === "/v1/jobs" && request.method() === "POST") {
      jobs = [completedJob];
      return route.fulfill({ json: completedJob });
    }
    if (path === "/v1/jobs") return route.fulfill({ json: { jobs } });
    if (path === "/files/preview.svg") return route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="768"><rect width="100%" height="100%" fill="#173d31"/></svg>',
    });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

test("connects to a worker and displays a completed generation", async ({ page }) => {
  await mockWorker(page);
  await page.addInitScript(() => {
    localStorage.setItem("local-via-worker", JSON.stringify({ url: "http://worker.test", token: "" }));
  });
  const browserErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/");
  const modalities = page.getByRole("navigation", { name: "Modalidades de generación" });
  await expect(modalities.getByRole("button", { name: "Texto → Imagen" })).toBeVisible();
  await expect(modalities.getByRole("button", { name: "Imagen → Imagen" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Creá una imagen desde una descripción." })).toBeVisible();
  await expect(page.getByRole("button", { name: /aula-pc-01/i })).toBeVisible({ timeout: 10_000 });
  await page.getByLabel("Instrucción creativa").fill(completedJob.prompt);
  await page.getByRole("button", { name: "Generar", exact: true }).click();
  await expect(page.getByRole("button", { name: /Ampliar preview\.svg/i })).toBeVisible({ timeout: 12_000 });
  await expect(page.getByRole("link", { name: "Descargar" }).first()).toBeVisible();
  await page.getByRole("button", { name: /Ampliar preview\.svg/i }).click();
  await expect(page.getByRole("button", { name: "Cerrar" })).toBeVisible();
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});
