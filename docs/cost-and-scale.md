# Cost and scale: intent mapper

Covers the intent mapper (`map_intent`) only. The explanation and email calls
are not included until they are measured.

## Tokens per call (measured)

Source: `scripts/run_ai_questions.py`, 20 questions, 13 real model calls.

| | Total | Average per call |
|---|---|---|
| Input tokens | 3,037 | about 234 |
| Output tokens | 214 | about 16 |

Input is mostly the list of 8 tasks in the instructions. Output is one task ID.

## Price

Model: `gpt-6-luna`, $0.10 per 1M input tokens and $0.50 per 1M output tokens
(OpenAI pricing page, checked Nov 16, 2026).

- About $0.000032 per model call
- About $0.032 per 1,000 model calls
- If each student asks 5 questions: about $0.16 per 1,000 students

Questions that code refuses before the model (work and status questions,
names and IDs, non-English text) cost $0. In our 20-question set, 7 of 20
made no model call, so real cost is lower than the figures above.

## What breaks first

1. The rate limit and the key's spend cap, long before the cost matters.
2. Free-tier hosting speed (cold starts), which the warm-up script covers.
3. Model latency: calls use a 30 second timeout and no retry.

## Limits of these numbers

- 20 questions is a small sample.
- Cost grows with the number of tasks, since every task is listed in each call.
- Explanation and email calls would add their own tokens and cost.
