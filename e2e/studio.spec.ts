import { expect, request, test, type Page } from "@playwright/test";

const PASSWORD = "alumno-dev-password";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  return errors;
}

async function login(page: Page, username: string, password = PASSWORD) {
  await page.goto("/");
  await page.getByLabel("Usuario").fill(username);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Creá una imagen desde una descripción." })).toBeVisible();
}

async function apiAs(baseURL: string, username: string) {
  const context = await request.newContext({ baseURL, extraHTTPHeaders: { "X-LocalVia": "1" } });
  expect((await context.post("/api/auth/login", { data: { username, password: PASSWORD } })).ok()).toBeTruthy();
  return context;
}

test("a student registers with a class code, generates and sees only their own work", async ({ page, baseURL }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "Crear cuenta" }).click();
  await page.getByLabel("Código de clase").fill("demo-2026");
  await page.getByLabel("Usuario").fill(`nuevo${Date.now() % 100000}`);
  await page.getByLabel("Contraseña").fill("una-clave-segura");
  await page.getByRole("button", { name: "Crear cuenta e ingresar" }).click();
  await expect(page.getByText(/computadoras libres/)).toBeVisible();
  await expect(page.getByText("Todavía no hiciste pedidos.")).toBeVisible();

  // Someone else's job must never appear in this student's history.
  const other = await apiAs(baseURL!, "alumno20");
  await other.post("/api/jobs", { data: { model: "z_image", task: "image.generate", prompt: "pedido privado de otra persona", parameters: {} } });

  await page.getByRole("button", { name: /Z.Image Turbo 6B/ }).click();
  await page.getByLabel("Instrucción creativa").fill("Una estación de tren bajo la lluvia");
  await page.getByRole("button", { name: "Generar", exact: true }).click();
  await expect(page.getByRole("button", { name: /Ampliar/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("pedido privado de otra persona")).toHaveCount(0);
  await page.getByRole("button", { name: /Ampliar/ }).click();
  await expect(page.getByRole("button", { name: "Cerrar" })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar" }).click();
  expect(errors).toEqual([]);
  await other.dispose();
});

test("queue position is shown while every computer is busy", async ({ page, baseURL }) => {
  const errors = watchErrors(page);
  const busy = [await apiAs(baseURL!, "alumno2"), await apiAs(baseURL!, "alumno8")];
  for (const context of busy) {
    const created = await context.post("/api/jobs", { data: { model: "z_image", task: "image.generate", prompt: "ocupa la computadora", parameters: {} } });
    expect(created.ok()).toBeTruthy();
  }
  await login(page, "alumno3");
  await page.getByRole("button", { name: /Z.Image Turbo 6B/ }).click();
  await page.getByLabel("Instrucción creativa").fill("Un faro al atardecer");
  await page.getByRole("button", { name: "Generar", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Puesto \d en la cola/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Tenés un pedido en curso" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Ampliar/ })).toBeVisible({ timeout: 30_000 });
  expect(errors).toEqual([]);
  for (const context of busy) await context.dispose();
});

test("image inputs are uploaded and used by the worker", async ({ page }) => {
  await login(page, "alumno4");
  await page.getByRole("navigation", { name: "Modalidades de generación" }).getByRole("button", { name: "Imagen → Imagen" }).click();
  await page.getByRole("button", { name: /Qwen Image Edit Plus Lightning 8/ }).click();
  await page.locator("input[type=file]").first().setInputFiles({ name: "escena.png", mimeType: "image/png", buffer: PNG });
  await page.getByLabel("Instrucción creativa").fill("Convertí la escena en una noche lluviosa");
  await page.getByRole("button", { name: "Generar", exact: true }).click();
  await expect(page.getByRole("button", { name: /Ampliar/ })).toBeVisible({ timeout: 30_000 });
});

test("a file that is not an image is rejected", async ({ page }) => {
  await login(page, "alumno5");
  await page.getByRole("navigation", { name: "Modalidades de generación" }).getByRole("button", { name: "Imagen → Imagen" }).click();
  await page.getByRole("button", { name: /Qwen Image Edit Plus Lightning 8/ }).click();
  await page.locator("input[type=file]").first().setInputFiles({ name: "falsa.png", mimeType: "image/png", buffer: Buffer.from("<script>alert(1)</script>") });
  await page.getByLabel("Instrucción creativa").fill("x");
  await page.getByRole("button", { name: "Generar", exact: true }).click();
  await expect(page.locator(".inlineError")).toContainText("El archivo no es una imagen");
});

test("administration: workers, class codes and model policy", async ({ page, baseURL }) => {
  const errors = watchErrors(page);
  await login(page, "admin", "admin-dev-password");
  await page.getByRole("link", { name: "Administración" }).click();
  await expect(page.getByRole("heading", { name: "Computadoras" })).toBeVisible();
  await expect(page.getByText("aula-pc-01")).toBeVisible();

  await page.getByRole("button", { name: "Clases" }).click();
  await page.getByLabel("Nombre").fill("Taller e2e");
  await page.getByRole("button", { name: "Crear código" }).click();
  await expect(page.getByRole("cell", { name: "Taller e2e" })).toBeVisible();

  await page.getByRole("button", { name: "Computadoras" }).click();
  await page.getByLabel("Nombre de la computadora").fill("aula-pc-99");
  await page.getByRole("button", { name: "Registrar" }).click();
  await expect(page.getByText("Token de aula-pc-99")).toBeVisible();

  await page.getByRole("button", { name: "Modelos y límites" }).click();
  await page.getByLabel("Z-Image Turbo 6B").uncheck();
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Guardado.")).toBeVisible();
  const student = await apiAs(baseURL!, "alumno6");
  const denied = await student.post("/api/jobs", { data: { model: "z_image", task: "image.generate", prompt: "x", parameters: {} } });
  expect(denied.status()).toBe(403);
  await page.getByLabel("Z-Image Turbo 6B").check();
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Guardado.")).toBeVisible();

  await page.getByRole("button", { name: "Auditoría" }).click();
  await expect(page.getByRole("cell", { name: "policy_updated" }).first()).toBeVisible();
  expect(errors).toEqual([]);
  await student.dispose();
});

test("students cannot open the administration API", async ({ baseURL }) => {
  const student = await apiAs(baseURL!, "alumno7");
  expect((await student.get("/api/admin/overview")).status()).toBe(403);
  const anonymous = await request.newContext({ baseURL });
  expect((await anonymous.get("/api/state")).status()).toBe(401);
  expect((await anonymous.post("/api/auth/login", { data: { username: "admin", password: "x" } })).status()).toBe(403);
  await student.dispose(); await anonymous.dispose();
});
