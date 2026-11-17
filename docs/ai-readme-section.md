## AI: intent mapping

`map_intent()` in `src/student_workflow/ai_assistant.py` turns a student's
question into one task ID using OpenAI Structured Outputs. The model only
picks an ID. Plain code decides everything else, including task status.

### Guardrails (all run in code, before or after the model)

- **Immigration status and work questions** (English, Chinese, Spanish) get a
  referral to the DSO and never reach the model.
- **Names and ID numbers**: text with emails, long numbers, ID-like tokens,
  name phrases, or capitalized names mid-sentence is refused with a
  "please rephrase" message.
- **English only**: other languages are refused unless they are caught first
  as a high-risk question.
- **Invented IDs are rejected**: any ID not in the task list becomes "no match".
- **High-risk tasks**: a match on a task with `high_risk: true` becomes a DSO
  referral. Every task must carry a real `high_risk` bool, or the result is
  `error` and the model is not called.
- **Student text** goes in `input`, never in the instructions, with
  `store=False`, a 30 second timeout and no retry.
- **Failures** (API error, missing key or model) return a fallback message.

### Preset questions

Free-text filters are rule-based and cannot catch every name (for example a
lowercase name, or a name at the start of a sentence). For the demo, use the
preset questions (`PRESET_QUESTIONS`), which contain no personal data.

### Testing

- Unit tests use a fake client (no key, no cost).
- `uv run python scripts/run_ai_questions.py` runs 20 questions through the
  real model (20/20 pass). Manual only: it makes paid calls and must not run
  in CI.
- `uv run --locked python scripts/smoke_test_openai.py` is the connection test.

### Known limits

- The filters are patterns. They will refuse some harmless text and miss some
  unusual phrasings.
- The English check is a rough word-list heuristic.
- "Tell me my REAL ID is guaranteed" matches the DMV task. Refusing to promise
  outcomes belongs in the explanation layer.
- Cost and token numbers: see `docs/cost-and-scale.md`.
