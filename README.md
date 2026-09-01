# Local Via

Local-first audiovisual AI studio for teaching and production. The interface can live on Vercel while the GPU work, model weights, inputs and outputs remain on a local RTX worker.

Local Via integrates [WanGP](https://github.com/deepbeepmeep/Wan2GP) and visibly discloses that backend in the UI and documentation, as required by WanGP's API terms.

## What is implemented

- Next.js 16 studio UI with the complete image/video/speech/SFX/music/edit model stack.
- Stable job API, model catalog, queue, progress, cancellation and restart recovery.
- Chunked 8 MB uploads and local SQLite history.
- Signed expiring output URLs with image, video and audio playback.
- One heavy CUDA job at a time.
- Embedded WanGP Python API adapter plus a deterministic mock backend for end-to-end testing without multi-gigabyte downloads.
- Local launch, tests and Vercel-ready static frontend.

## Run now

```powershell
./scripts/setup-local.ps1
./scripts/start-local.ps1
```

Open [http://localhost:3000](http://localhost:3000). The local configuration uses the real WanGP backend and does not ask for a token when both browser and worker are on localhost. Remote access still requires the private bearer token from the git-ignored `worker/.env`.

To stop it:

```powershell
./scripts/stop-local.ps1
```

## Enable the real GPU backend

```powershell
./scripts/install-wangp.ps1
```

The installer keeps checkpoints on `N:\local-via-models\ckpts` when that drive exists and enables the real backend. WanGP downloads the quantized assets required by a selected model on first use. Real smoke-test reports and generated media are stored under `N:\local-via-data\smoke-reports` and `N:\local-via-data\smoke-outputs`. See [the compatibility matrix](docs/MODEL_COMPATIBILITY.md).

To repeat a minimal real inference for one model:

```powershell
./.runtime/Wan2GP/env_conda/python.exe scripts/smoke_wangp_model.py qwen_image_edit_plus_20B
```

## Deploy the UI

For this client-only build, deploy the generated static directory:

```powershell
npm run build
npx vercel@58.11.0 deploy --prod
```

Run `npx vercel@58.11.0 login` first. The production UI for this project is [https://local-via.vercel.app](https://local-via.vercel.app). The browser must reach the worker over HTTPS; `./scripts/start-tunnel.ps1` creates only a temporary development tunnel. A stable Cloudflare hostname requires a named tunnel and a domain added to Cloudflare. See [architecture and tunnel setup](docs/ARCHITECTURE.md). No model or media file is sent to Vercel.

## Verification

```powershell
npm run lint
npm run typecheck
npm run build
worker/.venv/Scripts/python.exe -m pytest worker/tests -q
```
