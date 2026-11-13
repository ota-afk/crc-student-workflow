"""Manual live API smoke test. Uses a synthetic request and incurs API usage."""

from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from openai import APIError, OpenAI
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]


class RequestType(BaseModel):
    task: Literal["california_id", "school_check_in", "other"]


def main() -> int:
    config = dotenv_values(ROOT / ".env")
    key = config.get("OPENAI_API_KEY")
    model = config.get("OPENAI_MODEL")

    if not key or not model:
        print("FAIL: Set OPENAI_API_KEY and OPENAI_MODEL in .env.")
        return 1

    try:
        with OpenAI(
            api_key=key,
            base_url="https://api.openai.com/v1",
            timeout=30,
            max_retries=0,
        ) as client:
            response = client.responses.parse(
                model=model,
                instructions="Classify the user's request. Do not give advice.",
                input="I want to apply for a California ID.",
                text_format=RequestType,
                reasoning={"effort": "none"},
                max_output_tokens=200,
                store=False,
            )
    except (APIError, ValueError, ImportError) as error:
        print("FAIL:", type(error).__name__)
        print("HTTP status:", getattr(error, "status_code", "N/A"))
        print("Error code:", getattr(error, "code", "N/A"))
        return 1

    result = response.output_parsed
    if result is None:
        print("FAIL: No structured output received.")
        return 1

    print(result.model_dump_json(indent=2))
    if result.task != "california_id":
        print("FAIL: Unexpected classification.")
        return 1

    print("PASS: API connection, schema validation, and classification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
