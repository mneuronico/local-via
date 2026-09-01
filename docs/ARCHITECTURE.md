# Local Via architecture

```text
Next.js UI (local or Vercel)
          │ HTTPS + bearer token
          ▼
Cloudflare Tunnel (optional for remote access)
          │ localhost only
          ▼
FastAPI worker ── SQLite metadata
          │       local uploads/outputs
          ▼
WanGP Python API
          │ one CUDA job at a time
          ▼
RTX 2060 12 GB
```

The public web app never receives model weights and never stores generated media. It calls the selected worker directly. The worker is the security and compatibility boundary: it validates jobs, reconstructs chunked uploads, serializes GPU inference, maps the stable Local Via job schema to WanGP settings, signs temporary output links, and records reproducibility metadata.

## Job lifecycle

`queued → running → succeeded | failed | cancelled`

Only one `running` job is allowed. CPU-side upload assembly and metadata operations may happen concurrently. Jobs left in `queued` or `running` state after a restart are recovered into the queue.

## Storage

The default on this machine is `N:/local-via-data`, keeping large input/output files off the system drive. WanGP's `ckpts` path is a verified directory junction to `N:/local-via-models/ckpts` (about 4 TB was free when installed).

## Remote access

For localhost, use `http://127.0.0.1:9000`; browser requests from localhost do not need a copied token. The production UI is `https://local-via.vercel.app`. A Vercel-hosted HTTPS page must use an HTTPS worker URL and the private bearer token.

For a permanent worker URL, configure a named Cloudflare Tunnel to `http://localhost:9000`, add a published application hostname from a domain connected to the Cloudflare account, keep `https://local-via.vercel.app` in `LOCAL_VIA_ALLOWED_ORIGINS`, and set `LOCAL_VIA_PUBLIC_BASE_URL` to that hostname. Cloudflare requires a website/domain in the account for a published application route; the current account has no zone, so that final hostname cannot be created safely until a domain is explicitly selected and its DNS is delegated to Cloudflare.

For a short development session, run `./scripts/start-tunnel.ps1`. It prints a random `trycloudflare.com` URL. Quick Tunnels have no uptime guarantee and must be replaced by a named tunnel before classroom production.

The first version uses a worker bearer token plus HMAC-signed, expiring artifact URLs. A multi-user coordinator should mint short-lived per-job tokens and replace this shared token before classroom-wide use.
