# Release checklist: BE's Day 5 and demo day (STU-D05-BE)

The plan's BE Day 5 work: "Finish the README, run the key and git-history audit, run the
pre-recording check against the live API, warm up both live URLs, decide when the repo goes
public." This page is the order to do it in, and the results so far.

All commands run from the repo root. `.env.smoke` (git-ignored) holds the live `API_URL`,
`API_KEY` and `DASHBOARD_URL`; see [deploy.md](deploy.md#after-every-deploy-smoke-test).

## Before recording (Mon Nov 16)

1. **Warm up both services.** A free Render service sleeps after 15 idle minutes and takes
   about a minute to wake.

   ```bash
   uv run --env-file .env.smoke python scripts/warm_up.py
   ```

2. **Smoke test the live API.** Every endpoint, then the demo path.

   ```bash
   uv run --env-file .env.smoke python scripts/smoke_test.py
   ```

3. **Pre-recording check against the live API.** Fails on sample text, placeholder text,
   `is_mock`, or an unverified blocker. It also prints a warning listing every rule that is not
   verified yet: the dashboard shows those as "Not verified", and the voice-over must never
   state them as facts (the plan: "Say only verified facts").

   ```bash
   uv run --env-file .env.smoke python scripts/check_no_sample.py
   ```

4. Record. Warm up again first if more than 15 minutes have passed.

## Before the repo goes public

1. **Audit the whole git history for keys.** First fetch everything that becomes public with
   the repo, including GitHub's copy of every pull request (`refs/pull/...`), which a normal
   `git fetch` leaves out. Both commands only read; nothing on GitHub changes.

   ```bash
   git fetch origin '+refs/pull/*/head:refs/remotes/origin/pull/*'
   uv run --locked python scripts/audit_secrets.py
   ```

   It reads every commit reachable from your branches and the fetched refs, including what a
   merge commit itself changed and files that were renamed. It prints matches masked, and exits
   `1` on a key-shaped string or a committed secret file. Our own `API_KEY` has no fixed shape,
   so the audit looks for it next to its name (`API_KEY=...`, `"X-API-Key": "..."`).

   If it finds a real key: **rotate the key first** (make a new one, delete the old one at the
   provider), because removing it from the history doesn't un-leak it.
2. **Check the binary files by hand.** The audit can't read inside Word files; it lists them.
3. **Decide when the repo goes public** (team decision, see below).

## Results so far

| Check | Date | Result |
| --- | --- | --- |
| Key audit, all history | 2026-11-16 | Clean. 76 commits on all branches and the 21 fetched pull request refs, merges included: no key-shaped strings, no `.env`, key or secrets file ever committed (also not by rename). The scanner was tested on fake keys, a key typed into a merge, and a rename to `.env` (`tests/test_audit_secrets.py`). |
| Word files in history | 2026-11-16 | Clean. Every version of the three `docs/Day1_*.docx` files: no keys, no SEVIS-like numbers, no author name in the file properties. The only email address is CRC's public office address. |
| Commit emails | 2026-11-16 | **Team decision.** 5 commit email addresses are not GitHub "noreply" addresses, so they become public with the history. See below. |
| Pre-recording check, live engine on a laptop | 2026-11-16 | Passes. Warning: all 8 cited rules are still `needs_verification`. |
| Pre-recording check, live API | Not run yet | Needs the deploy (docs/deploy.md). |
| Warm-up, both live URLs | Not run yet | Needs the deploy. |

## Team decisions (not BE's alone)

- **When the repo goes public.** The plan: submissions are public, and Devpost needs a repo
  link that works for someone not on the team. Run the audit again right before switching it.
- **Commit emails.** Some teammates' commits show a real email address, which becomes public
  with the repo. Rewriting shared history is drastic and needs everyone's agreement. The light
  option: each person turns on GitHub's "Keep my email addresses private" (Settings → Emails)
  and sets git's `user.email` to their noreply address, so future commits are private. Run
  `uv run --locked python scripts/audit_secrets.py` to see the count; it never prints the
  addresses.
- **Unverified rules in the video.** Every rule ENG has cited is still `needs_verification`.
  The demo can show them labeled "Not verified", but the plan's video rules say to state only
  verified facts. ENG's second checks decide what can be said.
