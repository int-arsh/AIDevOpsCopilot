"""Groq API client factory and thin wrappers for llama-3.3-70b-versatile chat completions."""

import os

from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

_api_key = os.getenv("GROQ_API_KEY")
if not _api_key:
    raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")

groq_client = AsyncGroq(api_key=_api_key)


async def ask_groq(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request to Groq and return the assistant reply text.

    Args:
        system_prompt: Instructions that define the assistant's behavior.
        user_message: The user's input message.
        max_tokens: Maximum number of tokens to generate in the response.

    Returns:
        The assistant's response content as a plain string.

    Raises:
        RuntimeError: If the Groq API call fails for any reason.
    """
    try:
        completion = await groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError(f"Groq API call failed: {exc}") from exc


if __name__ == "__main__":
    import asyncio

    async def _run_test() -> None:
        """Send a quick hello prompt and print the model response."""
        response = await ask_groq(
            system_prompt="You are a DevOps expert.",
            user_message="Say hello.",
        )
        print(response)

    asyncio.run(_run_test())
