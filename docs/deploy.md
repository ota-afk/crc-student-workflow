# Deploying the API and the dashboard (STU-D04-BE)

Both services run on Render's free plan, set up from [`render.yaml`](../render.yaml) (a Render
"Blueprint": one file that describes both services). Only the BE owner's Render account is
used; teammates don't need one.

**Status (2026-11-16): deployed from `main`.** The API passed the full smoke test. The dashboard
is up, but its calls get `401` until FE's change that sends the API key is on `main`; Render
redeploys it by itself once that merges and CI passes.

## Live URLs

| Service | URL |
| --- | --- |
| API | https://crc-workflow-api.onrender.com |
| Dashboard | https://crc-workflow-dashboard.onrender.com |

## Before the first deploy: the dashboard must send the API key

The deployed API needs the `X-API-Key` header on every endpoint except `/health`
([contract](contract.md#access-api-key-and-rate-limit)). The dashboard on `main` does
not send it yet, and it only calls `GET /workflow`. So:

- **FE** adds the header (from the dashboard's `API_KEY` setting) to every request, and wires
  onboarding, "Resolve blocker" and "Mark done" to the `POST` endpoints.
- Until that is merged, a deployed dashboard gets `401` from a deployed API. Deploy the API
  first and smoke test it (below); deploy the dashboard once FE's change is on `main`.

## One-time setup

1. **Make the API key.** On your computer, run:

   ```bash
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   This prints a long random string. It is the shared secret between our two services. Keep
   it in a password manager; never paste it into chat, code, a commit or the video.
2. In Render: **New → Blueprint**, pick the `ota-afk/crc-student-workflow` repo, branch `main`.
   Render reads `render.yaml` and lists the two services.
3. Render asks for the values marked `sync: false`. The URLs below are examples: a service's
   real address is shown on its page in Render once it exists, and it may not match the
   service name exactly. Use the real ones.

   | Service | Setting | Value |
   | --- | --- | --- |
   | `crc-workflow-api` | `API_KEY` | The key from step 1 |
   | `crc-workflow-api` | `CORS_ORIGINS` | The dashboard's URL, e.g. `https://crc-workflow-dashboard.onrender.com` |
   | `crc-workflow-dashboard` | `API_URL` | The API's URL, e.g. `https://crc-workflow-api.onrender.com` |
   | `crc-workflow-dashboard` | `API_KEY` | The same key from step 1 |

   Render only asks once, when the Blueprint is created. To change a value later, edit it on
   the service's **Environment** page and save, then check the service's **Events** page that
   it redeployed with the new value.
4. **Apply.** Render builds both services (`uv sync --locked --no-dev`) and starts them. The API
   is ready when `https://<api-url>/health` shows `{"status":"ok"}`.
5. Put both URLs in the "Live URLs" table above (a small docs pull request).

After this, every merge to `main` deploys both services once CI passes (`autoDeployTrigger:
checksPass`). The OpenAI key is not needed yet: the backend makes no OpenAI calls until the AI
layer (#15) is wired in. When it is, add `OPENAI_API_KEY` and `OPENAI_MODEL` on the API's
Environment page only, never in `render.yaml`.

## After every deploy: smoke test

From the repo on your computer, make a file named `.env.smoke` (git-ignored, like `.env`) with
these lines (`DASHBOARD_URL` is for the warm-up script):

```text
API_URL=https://<api-url>
API_KEY=<the key>
DASHBOARD_URL=https://<dashboard-url>
```

Then run:

```bash
uv run --env-file .env.smoke python scripts/smoke_test.py
```

A separate file, not `.env`: the API and dashboard read `.env` when they start, so live values
there would make your local runs call the live API. Typing the key on the command line instead
would save it in your shell history.

It checks every endpoint, checks that a request without the key is refused and that
`GET /workflow` is live data (not the mock), and walks the demo
path (DMV Blocked, then residency In Progress, then DMV Ready). Each passing step prints `ok`,
and the last line is `All checks passed`. Any `FAIL` line says which request failed and the
API's reason. CI runs the same script against a fresh local server on every pull request.

## Free plan: what to expect

- **Sleeping.** A free service sleeps after 15 minutes without traffic, and the next request
  takes about a minute while it wakes up. Wake both services before recording or judging
  with `uv run --env-file .env.smoke python scripts/warm_up.py`; the order for demo day is in
  [release-checklist.md](release-checklist.md). The smoke test waits up to two minutes for
  `/health`.
- **750 free hours per month** for the whole Render workspace. Two services awake all month
  would need about 1,440, so check the usage on Render's billing page before judging (Nov 20)
  and until winners are announced (around Nov 30), when the plan says the link must stay up.
- **No private network.** Free services can't receive private traffic, so the dashboard calls
  the API's public `https` URL.
- **No disk.** Files written at runtime disappear on restart. We store nothing, so nothing
  is lost.

## Rate limit behind Render

Render's docs don't say what forwarded-address headers contain, so the API doesn't trust them.
Instead, requests with the right key (the dashboard's server) share one allowance of
`RATE_LIMIT`, and every other request is counted by the address the API sees. Requests without
the key are refused anyway (`401`), and they can never use up the dashboard's allowance. The
allowance covers all endpoints together, so calling a different path or task ID doesn't get a
fresh one. `/health` is never limited.

## Troubleshooting

- **Deploy fails at "health check".** Open the service's **Logs**. An invalid `RATE_LIMIT`
  stops the API at startup with a message naming it.
- **Dashboard shows "Could not reach the API".** Check `API_URL` on the dashboard (https, no
  trailing path), and that the API's `/health` answers. The API may be waking up: wait a
  minute and reload.
- **Smoke test says `no key gave 200, not 401`.** `API_KEY` is empty on the API: set it.
- **Smoke test says `GET /workflow returned mock data`.** Set `USE_MOCK=false` on the API.
- **First deploy: check the log once.** Confirm the API's log shows `Uvicorn running on
  http://0.0.0.0:<port>` with Render's port, not 8000. These start commands were tested in a
  clean copy on a laptop, but not yet on Render itself.
- **Smoke test gets `401` on `/schools`.** The `API_KEY` you passed doesn't match the API's.
