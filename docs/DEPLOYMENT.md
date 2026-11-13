# Deployment

## Option in use: temporary public link (Cloudflare quick tunnel)

Free, with no account and no router changes. `cloudflared` opens an outbound connection from this laptop to Cloudflare,
which gives a random `https://<words>.trycloudflare.com` address. The site keeps using the local MySQL database and models.

| Action | Command |
|---|---|
| Go public | `.\scripts\public_start.ps1` (prints the link and saves it to `run\public_url.txt`) |
| Check | `.\scripts\public_status.ps1` |
| Stop being public | `.\scripts\public_stop.ps1` (closes the link and restarts the app in local-only mode) |

**What changes in public mode** (`PUBLIC_MODE=1`, set only for the app process started by `public_start.ps1`):
- The app trusts exactly **one** proxy (cloudflared) for `X-Forwarded-For/Proto/Host`. Rate limits, account lockouts and
  audit IP hashes therefore apply per real visitor. The app still listens only on `127.0.0.1`, so those headers can only
  come from the local tunnel.
- Session cookies are marked `Secure` (visitors reach the site over HTTPS).

**Limits to know**
- **Works only while the laptop is on**, awake and online. Sleep or shutdown takes the site offline.
- **The address changes** every time `public_start.ps1` runs. Quick tunnels are meant for testing and demos, with no
  uptime guarantee.
- **Anyone with the link can register and upload photos**, and those photos are stored on this laptop. Share the link only
  with people you trust, and stop it when you're done.
- `cloudflared.exe` lives in `tools\`, which is git-ignored. To get it, download `cloudflared-windows-amd64.exe` from
  https://github.com/cloudflare/cloudflared/releases, check that its digital signature is from "Cloudflare, Inc.", and
  save it as `tools\cloudflared.exe`.

## Options for a permanent site (not set up)

| Option | Notes |
|---|---|
| Railway | About $5–10/month: app, managed MySQL and a volume for photos in one place, with a permanent HTTPS address |
| Hugging Face Spaces (Docker) | Free tier has 16 GB RAM, but no persistent storage unless you use an external MySQL |
| Own Linux VM | Most control: Docker, Waitress/Gunicorn behind Nginx with HTTPS, `ProductionConfig` |

The AI needs about 2 GB of RAM, so free 512 MB plans can't run it. All options must stay **non-commercial**
because of the HAM10000 licence.
