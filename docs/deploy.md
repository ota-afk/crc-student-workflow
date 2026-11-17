# Deploying the API and the dashboard (STU-D04-BE)

Both services run on Render's free plan, set up from [`render.yaml`](../render.yaml) (a Render
"Blueprint": one file that describes both services). Only the BE owner's Render account is
used; teammates don't need one.

**Status (2026-11-17): both services deployed from `main`.** The API passes the full smoke test.
The dashboard sends the API key and calls the `POST` endpoints since FE's #30; its code was
walked through against the live API (results in [release-checklist.md](release-checklist.md)).

## Live URLs

| Service | URL |
| --- | --- |
| API | https://crc-workflow-api.onrender.com |
| Dashboard | https://crc-workflow-dashboard.onrender.com |

The dashboard service runs **Flyover** (`app/flyover_app.py`), the team's demo since Nov 17.
Flyover's client (`src/student_workflow/flyover_client.py`) sends the same `X-API-Key` and
calls the same endpoints, including `POST /assistant`, so it needs no extra settings. Changing
`startCommand` in `render.yaml` reaches Render through the Blueprint: if the service's
**Settings** page still shows the old command after the merge deploys, click **Manual sync**
on the Blueprint page.

## The dashboard and the API key

The deployed API needs the `X-API-Key` header on every endpoint except `/health`
([contract](contract.md#access-api-key-and-rate-limit)). The dashboard sends it on every
request from its own `API_KEY` setting (`src/student_workflow/frontend_api.py`, FE's #30), so
both services must have the same `API_KEY` on Render. Streamlit runs on the server, so the key
never reaches a visitor's browser.

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
checksPass`).

## Enable the Assistant API

Set `OPENAI_API_KEY` and `OPENAI_MODEL` on the `crc-workflow-api` Render Environment page.
Use a model supported by the existing AI helpers and keep the key in Render's service
environment. After redeploy, make an authenticated `POST /assistant` using the request
example in the [Assistant API contract](contract.md#post-assistant). Confirm the answer
matches the current task and that a status or work-authorization question returns a DSO
referral.

Then set `ASSISTANT_MODE` to `live` on the `crc-workflow-dashboard` Environment page. The
dashboard calls `POST /assistant` at its `API_URL` with its `API_KEY`; there is no separate
assistant URL to set. Check it in the browser:

1. Generate a workflow, open the REAL ID task, and ask "Why is my ID blocked?". The answer
   says `Task status: Blocked.`
2. **Resolve blocker**, ask again: still Blocked, with residency awaiting a reply.
3. Mark residency done, ask again: the answer says `Task status: Ready.`
4. Ask "Can I work off campus?": the answer refers you to the DSO.

If the API was asleep, the first question may show "The assistant took too long to answer";
ask again after a minute.

## Reminder emails (Resend)

On `crc-workflow-api` → Environment:

| Setting | Value |
| --- | --- |
| `RESEND_API_KEY` | The team's Resend API key (only here, never in code or chat). |
| `REMINDER_RECIPIENTS` | Comma-separated addresses the demo may email, e.g. the Resend account owner's address. Empty = nobody. |
| `REMINDER_FROM` | Optional. Default `Flyover <onboarding@resend.dev>`, Resend's test sender. |

Until the team verifies its own domain in Resend, use the test sender and an address the
account owner controls. Check: sign in to Flyover with an allowed address, schedule a reminder
a few minutes ahead, close the browser, and confirm it arrives.

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
- **Dashboard shows "Could not load your workflow".** Most often the API was asleep: the
  dashboard gives up after 10 seconds, and waking takes about a minute. Wait a minute and click
  Retry, or run `scripts/warm_up.py` first. If it keeps failing, check `API_URL` on the
  dashboard (https, no trailing path) and that the API's `/health` answers.
- **Smoke test says `no key gave 200, not 401`.** `API_KEY` is empty on the API: set it.
- **Smoke test says `GET /workflow returned mock data`.** Set `USE_MOCK=false` on the API.
- **A service won't start after a `render.yaml` change.** Check its log: the API should show
  `Uvicorn running on http://0.0.0.0:<port>` with Render's port, not 8000. Both start commands
  have run on Render since the first deploy (Nov 2026).
- **Smoke test gets `401` on `/schools`.** The `API_KEY` you passed doesn't match the API's.
