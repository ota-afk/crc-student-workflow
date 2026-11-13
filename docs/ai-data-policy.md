# AI Data Policy

## Scope

These are requirements for the AI integration.
The Day 1 smoke test sends one fixed synthetic request.
Passing that test does not verify privacy or guardrail enforcement
throughout the application.

## Never include in model input

- Real student names.
- Passport numbers, real SEVIS IDs, or SSN numbers.
- Passport, visa, I-20, or other personal document files or images.
- Personal email addresses, phone numbers, or home addresses.
- Payment details, passwords, API keys, or other credentials.

API keys are used only for API authentication, never as prompt content.

## Minimum necessary context

When needed for a specific feature, model input may include:

- School identifier, state, visa category, and relevant dates.
- Whether a student has an SSN, never the SSN itself.
- Self-reported readiness checkboxes.
- Task IDs, engine-computed task states, and missing prerequisites.
- Rule text, source references, and verification status.

Remove identifying information from free-text requests before sending them.
If safe processing is uncertain, ask the user to rephrase without personal data.

## Product requirements

- Do not accept document uploads.
- Readiness is self-reported, not document verification.
- The rule engine determines task status; the AI explains and drafts.
- Preserve unverified labels and never invent requirements or citations.
- Refer immigration-status and work-authorization questions to the DSO
  or official sources instead of giving definitive answers.
- Email drafts use placeholders such as [YOUR NAME].
- Users complete and send emails themselves.
- Do not send emails or persist email drafts in the application.

## Smoke test

Run manually from the repository root:

    uv run --locked python scripts/smoke_test_openai.py

The test reads credentials from the local .env file.
It uses a synthetic request, store=False, a 30-second timeout,
zero automatic retries, and a 200-token output limit.
It prints the parsed result or error identifiers, never the API key.
It makes a paid API request and must not run automatically in CI.
Test labels do not define the final workflow task IDs.

## Secrets

Keep .env and secret backups out of Git.
Use deployment secret settings for hosted credentials.
Revoke exposed keys and update local or deployment configuration.
