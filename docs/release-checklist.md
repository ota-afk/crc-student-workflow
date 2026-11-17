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
3. **Check your working files too.** The audit reads committed history only, never files you
   haven't committed. Run `git status` and make sure nothing secret is about to be added.
4. **Decide when the repo goes public** (team decision, see below).

### What the audit can't prove

It is a set of patterns, not proof that no secret or personal data is in the history:

- It finds known key shapes (OpenAI, AWS, GitHub, private-key blocks), and any literal value
  written next to a name like `api_key`, `secret`, `token` or `password`. That includes values
  without digits and Render's two-line `key:` / `value:` settings. It skips placeholders
  (`<...>`, `${...}`) and code that reads a setting (`os.getenv(...)`).
- A secret under an unrelated name, or pasted into prose, can slip through.
- It can't read binary files (Word, PDF, images); it lists them for a hand check.
- It reads history, not uncommitted files.
- For personal data it only counts commit emails. Names, SEVIS IDs or passport numbers in files
  are not searched for (the Word files were checked by hand once, see below).

## Results so far

| Check | Date | Result |
| --- | --- | --- |
| Key audit, all history | 2026-11-17 | No findings. 139 commits on all branches and the 30 fetched pull request refs (main at #30), merges included: no key-shaped strings or literal secret assignments, no `.env`, key or secrets file ever committed (also not by rename). Tested on fake keys, a key typed into a merge, a rename to `.env`, digit-free and quoted secrets, and Render `key:`/`value:` pairs (`tests/test_audit_secrets.py`). Not proof; see "What the audit can't prove". |
| Word files in history | 2026-11-16 | Clean. Every version of the three `docs/Day1_*.docx` files: no keys, no SEVIS-like numbers, no author name in the file properties. The only email address is CRC's public office address. |
| Commit emails | 2026-11-17 | **Already public.** The repo is public, and 7 commit email addresses are not GitHub "noreply" addresses. See below. |
| Pre-recording check, live engine on a laptop | 2026-11-16 | Passes (`USE_MOCK=false`, local server). Warning: all 8 cited rules are still `needs_verification`. Not a check of the deployed API. |
| Smoke test, live API | 2026-11-17 | `All checks passed` against the deployed API (main at #30): every endpoint, the key check, and the demo path. |
| Pre-recording check, live API | 2026-11-17 | `clean`. Warning: 19 cited rules are still `needs_verification` (1 of the 21 rules in `rules.json` is verified). |
| Dashboard walkthrough, live API | 2026-11-17 | Passes. The dashboard code on main (#30), run on a laptop against the deployed API: load, school search, generate (DMV Blocked), resolve (draft shown, residency In Progress), mark done (DMV Ready), reload (still Ready). Clicking through the deployed dashboard in a browser is still to do. |
| Warm-up, both live URLs | 2026-11-17 | Both awake. A sleeping API makes the dashboard's first load fail after its 10-second timeout; Retry works about a minute later. Warm up before recording and before judging. |

## Team decisions (not BE's alone)

- **The repo is public** (made public for Render). The audit above was run after that, on
  2026-11-17.
- **Commit emails.** Some teammates' commits show a real email address, which is public
  with the repo. Rewriting shared history is drastic and needs everyone's agreement. The light
  option: each person turns on GitHub's "Keep my email addresses private" (Settings → Emails)
  and sets git's `user.email` to their noreply address, so future commits are private. Run
  `uv run --locked python scripts/audit_secrets.py` to see the count; it never prints the
  addresses.
- **Unverified rules in the video.** 1 of the 21 rules is verified; 19 rules the workflow
  cites are still `needs_verification`. The demo can show them labeled "Not verified", but the
  plan's video rules say to state only verified facts. ENG's second checks decide what can be
  said.
