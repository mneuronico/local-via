// Real bandwidth measurement for Local Via.
//
// Every simulated student uses a real Chromium browser through the real UI, connected to the real hub
// over HTTPS. Each browser goes through its own byte-counting TCP relay, so the numbers are the bytes
// that actually cross the network (HTTP + TLS), per student and per second. The lab workers are mock
// workers (no GPU) that return real files previously generated on the RTX 2060 (data/bandwidth-samples).
//
// Usage:  node scripts/measure-bandwidth.mjs [--quick]
// Output: docs/bandwidth/results.json
import { chromium } from "@playwright/test";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, statSync, writeFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1")), "..");
const QUICK = process.argv.includes("--quick");
const HUB_PORT = 8095;
const WORKER_PROXY_PORT = 8195;
const PASSWORD = "alumno-dev-password";
const SAMPLES = path.join(ROOT, "data", "bandwidth-samples");
const MOCK_SECONDS = QUICK ? 20 : 60;
const IDLE_SECONDS = QUICK ? 30 : 120;
const PYTHON = process.platform === "win32" ? path.join(ROOT, ".venv", "Scripts", "python.exe") : path.join(ROOT, ".venv", "bin", "python");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** TCP relay that counts bytes in both directions and keeps a per-second timeline. */
class Meter {
  constructor(name, listenPort, targetPort) {
    Object.assign(this, { name, listenPort, targetPort, up: 0, down: 0, connections: 0, timeline: new Map() });
    this.server = net.createServer((client) => {
      this.connections += 1;
      const upstream = net.connect(targetPort, "127.0.0.1");
      const count = (direction) => (chunk) => {
        this[direction] += chunk.length;
        const second = Math.floor(Date.now() / 1000);
        const slot = this.timeline.get(second) ?? { up: 0, down: 0 };
        slot[direction] += chunk.length; this.timeline.set(second, slot);
      };
      client.on("data", count("up")); upstream.on("data", count("down"));
      client.pipe(upstream); upstream.pipe(client);
      const close = () => { client.destroy(); upstream.destroy(); };
      client.on("error", close); upstream.on("error", close); client.on("close", close); upstream.on("close", close);
    });
  }
  listen() { return new Promise((resolve) => this.server.listen(this.listenPort, "127.0.0.1", resolve)); }
  snapshot() { return { up: this.up, down: this.down, at: Date.now() }; }
  close() { this.server.close(); }
}

function delta(from, to) {
  const seconds = (to.at - from.at) / 1000;
  return { seconds: +seconds.toFixed(1), up_bytes: to.up - from.up, down_bytes: to.down - from.down, total_bytes: to.up - from.up + to.down - from.down,
    avg_kbit_s: seconds > 0 ? +(((to.up - from.up + to.down - from.down) * 8) / 1000 / seconds).toFixed(2) : null };
}

async function waitForHub() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      await new Promise((resolve, reject) => { const socket = net.connect(HUB_PORT, "127.0.0.1", () => { socket.destroy(); resolve(); }); socket.on("error", reject); });
      await sleep(2500); return;
    } catch { await sleep(500); }
  }
  throw new Error("El hub no arrancó");
}

let port = 9200;
async function student(browser, username) {
  const meter = new Meter(username, port++, HUB_PORT); await meter.listen();
  const context = await browser.newContext({ ignoreHTTPSErrors: true, acceptDownloads: true, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const base = `https://localhost:${meter.listenPort}`;
  return { meter, context, page, base, username };
}

async function login(s) {
  await s.page.goto(`${s.base}/`);
  await s.page.getByLabel("Usuario").fill(s.username);
  await s.page.getByLabel("Contraseña").fill(PASSWORD);
  await s.page.getByRole("button", { name: "Ingresar", exact: true }).click();
  await s.page.getByText(/computadoras libres/).waitFor({ timeout: 30_000 });
  await s.page.waitForLoadState("networkidle");
}

const FLOWS = {
  image: { workflow: "Texto → Imagen", model: /^Z.Image Turbo 6B$/, prompt: "Un faro en la costa al atardecer, fotografía", output: "image.jpg" },
  video: { workflow: "Imagen → Video", model: /^Wan 2\.2 TI2V 5B$/, prompt: "La cámara avanza lentamente hacia el faro", input: "input-image.jpg", output: "video.mp4" },
  audio: { workflow: "Texto → Música", model: /^ACE.Step 1\.5 Turbo$/, prompt: "Instrumental de persecución con campanas", output: "audio.wav" },
};

/** One full student interaction through the UI; returns byte counts per phase. */
async function generate(s, kind, { download = true } = {}) {
  const flow = FLOWS[kind]; const marks = {};
  await s.page.getByRole("navigation", { name: "Modalidades de generación" }).getByRole("button", { name: flow.workflow, exact: true }).click();
  await s.page.locator(".modelCard").filter({ has: s.page.locator("h3", { hasText: flow.model }) }).first().click();
  if (flow.input) await s.page.locator("input[type=file]").first().setInputFiles(path.join(SAMPLES, flow.input));
  await s.page.locator("#prompt").fill(flow.prompt);
  // Hold result files until the job is reported done, so waiting (polling) and viewing are measured apart.
  let release; const gate = new Promise((resolve) => { release = resolve; });
  const hold = async (route) => { await gate; await route.continue().catch(() => undefined); };
  await s.page.route("**/api/files/**", hold);
  marks.submit = s.meter.snapshot();
  await s.page.getByRole("button", { name: "Generar", exact: true }).click();
  await s.page.locator(".jobState.queued, .jobState.running").first().waitFor({ timeout: 60_000 });
  marks.accepted = s.meter.snapshot();
  await s.page.getByRole("button", { name: /Ampliar/ }).waitFor({ timeout: 30 * 60_000 });
  marks.done = s.meter.snapshot();
  release(); await s.page.unrouteAll({ behavior: "wait" });
  await s.page.waitForLoadState("networkidle");
  await s.page.getByRole("button", { name: /Ampliar/ }).click();
  if (kind === "video") await s.page.waitForFunction(() => { const v = document.querySelector(".viewerCanvas video"); return v && v.readyState >= 4; }, null, { timeout: 60_000 });
  if (kind === "audio") {
    // play() may never resolve in headless Chromium (no audio device), so it is not awaited.
    await s.page.locator(".viewerCanvas audio").evaluate((audio) => { audio.play().catch(() => undefined); });
    await s.page.waitForFunction(() => { const a = document.querySelector(".viewerCanvas audio"); return a && a.readyState >= 4; }, null, { timeout: 60_000 });
  }
  await s.page.waitForLoadState("networkidle"); await sleep(1500);
  marks.viewed = s.meter.snapshot();
  await s.page.getByRole("button", { name: "Cerrar" }).click();
  if (download) {
    const [file] = await Promise.all([s.page.waitForEvent("download"), s.page.locator(".artifactActions a").click()]);
    await Promise.race([file.path(), sleep(120_000).then(() => { throw new Error("download timeout"); })]); await sleep(500);
  }
  marks.downloaded = s.meter.snapshot();
  console.log(`[medición] ${s.username} ${kind}: listo`);
  return {
    output_file_bytes: statSync(path.join(SAMPLES, flow.output)).size,
    input_file_bytes: flow.input ? statSync(path.join(SAMPLES, flow.input)).size : 0,
    upload_and_submit: delta(marks.submit, marks.accepted),
    waiting_while_queued_or_running: delta(marks.accepted, marks.done),
    view_result: delta(marks.done, marks.viewed),
    download_result: delta(marks.viewed, marks.downloaded),
    job_total: delta(marks.submit, marks.downloaded),
  };
}

async function main() {
  mkdirSync(path.join(ROOT, "docs", "bandwidth"), { recursive: true });
  const workerMeter = new Meter("workers", WORKER_PROXY_PORT, HUB_PORT); await workerMeter.listen();
  const hub = spawn(PYTHON, ["scripts/dev_classroom.py", "--tls", "--workers", "8", "--students", "30", "--port", String(HUB_PORT), "--mock-seconds", String(MOCK_SECONDS),
    "--samples-dir", SAMPLES, "--reset", "--data-dir", "data/bandwidth-classroom", "--worker-hub-url", `https://localhost:${WORKER_PROXY_PORT}`], { cwd: ROOT, stdio: "ignore" });
  // Never leave the simulated classroom running, even if the measurement crashes.
  process.on("exit", () => { if (process.platform === "win32") spawnSync("taskkill", ["/F", "/T", "/PID", String(hub.pid)]); else hub.kill(); });
  const results = { measured_at: new Date().toISOString(), method: {}, single_user: {}, concurrency: {} };
  const browser = await chromium.launch();
  try {
    await waitForHub(); await sleep(4000);
    results.method = {
      transport: "HTTPS (TLS 1.3, HTTP/1.1) through a byte-counting TCP relay per student; bytes are TCP payload (TLS records included, TCP/IP headers excluded).",
      browser: `Chromium ${browser.version()} via Playwright, cold cache per student`,
      workers: `8 mock workers returning real RTX 2060 outputs; simulated job duration ${MOCK_SECONDS} s`,
      samples: Object.fromEntries(["image.jpg", "video.mp4", "audio.wav", "input-image.jpg"].map((name) => [name, statSync(path.join(SAMPLES, name)).size])),
    };

    // 1) First load + an idle, logged-in session.
    const idle = await student(browser, "alumno1");
    const start = idle.meter.snapshot();
    await login(idle);
    const loaded = idle.meter.snapshot();
    await sleep(IDLE_SECONDS * 1000);
    results.single_user.first_load_and_login = delta(start, loaded);
    results.single_user.idle_logged_in = delta(loaded, idle.meter.snapshot());
    const reloadStart = idle.meter.snapshot();
    await idle.page.reload(); await idle.page.getByText(/computadoras libres/).waitFor(); await idle.page.waitForLoadState("networkidle");
    results.single_user.reload_with_warm_cache = delta(reloadStart, idle.meter.snapshot());
    await idle.context.close(); idle.meter.close();

    // 2) One complete job per output type, alone in the room.
    for (const [kind, username] of [["image", "alumno2"], ["video", "alumno3"], ["audio", "alumno4"]]) {
      const s = await student(browser, username); await login(s);
      results.single_user[`${kind}_job`] = await generate(s, kind);
      console.log(kind, JSON.stringify(results.single_user[`${kind}_job`].job_total));
      await s.context.close(); s.meter.close();
    }
    results.lan_hub_to_workers_single_user_phase = { up_bytes: workerMeter.up, down_bytes: workerMeter.down, note: "worker→hub uploads count as 'up'" };

    // 3) Twelve students at once: eight generate immediately, four wait in the queue.
    const lanBefore = workerMeter.snapshot();
    const crowd = [];
    for (let index = 0; index < 12; index++) { const s = await student(browser, `alumno${10 + index}`); await login(s); crowd.push(s); }
    console.log("[medición] 12 estudiantes conectados; envían a la vez");
    const begin = Date.now(); const before = crowd.map((s) => s.meter.snapshot());
    const outcomes = await Promise.all(crowd.map((s) => generate(s, "video")));
    const end = Date.now();
    const seconds = new Map();
    for (const s of crowd) for (const [second, slot] of s.meter.timeline) {
      if (second * 1000 < begin - 1000 || second * 1000 > end + 1000) continue;
      const total = seconds.get(second) ?? 0; seconds.set(second, total + slot.up + slot.down);
    }
    const series = [...seconds.entries()].sort((a, b) => a[0] - b[0]).map(([second, bytes]) => ({ t: second - Math.floor(begin / 1000), kbit_s: +((bytes * 8) / 1000).toFixed(1) }));
    const totalBytes = crowd.reduce((sum, s, index) => sum + (s.meter.up - before[index].up) + (s.meter.down - before[index].down), 0);
    results.concurrency.twelve_students_video = {
      students: 12, generating_at_once: 8, queued: 4, duration_seconds: +((end - begin) / 1000).toFixed(1),
      total_bytes: totalBytes, avg_kbit_s: +((totalBytes * 8) / 1000 / ((end - begin) / 1000)).toFixed(1),
      peak_1s_kbit_s: Math.max(...series.map((point) => point.kbit_s)),
      per_student_total_bytes: outcomes.map((outcome) => outcome.job_total.total_bytes),
      per_student_waiting_kbit_s: outcomes.map((outcome) => outcome.waiting_while_queued_or_running.avg_kbit_s),
      lan_hub_workers: delta(lanBefore, workerMeter.snapshot()),
      series,
    };
    for (const s of crowd) { await s.context.close(); s.meter.close(); }
  } finally {
    await browser.close(); workerMeter.close();
    // The classroom spawns the hub and workers as children; kill the whole tree.
    if (process.platform === "win32") spawnSync("taskkill", ["/F", "/T", "/PID", String(hub.pid)]); else hub.kill();
  }
  const target = path.join(ROOT, "docs", "bandwidth", QUICK ? "results-quick.json" : "results.json");
  writeFileSync(target, JSON.stringify(results, null, 2));
  console.log(`Resultados: ${target}`);
  console.log(JSON.stringify({ ...results, concurrency: { ...results.concurrency, twelve_students_video: { ...results.concurrency.twelve_students_video, series: "(omitted)" } } }, null, 2));
}

main().catch((error) => { console.error(error); process.exit(1); });
