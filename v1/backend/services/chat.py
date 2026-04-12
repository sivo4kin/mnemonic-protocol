"""Chat provider adapters — Anthropic, OpenAI, Qwen."""
from __future__ import annotations

from ..config import settings


async def generate_response(
    provider: str,
    model: str,
    system_prompt: str,
    messages: list[dict],
) -> str:
    """Call a chat provider and return the assistant response text."""
    if provider == "anthropic":
        return await _anthropic_generate(model, system_prompt, messages)
    elif provider == "openai":
        return await _openai_generate(model, system_prompt, messages, settings.OPENAI_API_KEY)
    elif provider == "qwen":
        return await _qwen_generate(model, system_prompt, messages)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _anthropic_generate(model: str, system_prompt: str, messages: list[dict]) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


async def _openai_generate(
    model: str, system_prompt: str, messages: list[dict],
    api_key: str, base_url: str | None = None,
) -> str:
    import openai
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.AsyncOpenAI(**kwargs)
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    response = await client.chat.completions.create(
        model=model,
        messages=full_messages,
        max_tokens=4096,
    )
    return response.choices[0].message.content


async def _qwen_generate(model: str, system_prompt: str, messages: list[dict]) -> str:
    return await _openai_generate(
        model, system_prompt, messages,
        api_key=settings.QWEN_API_KEY,
        base_url=settings.QWEN_BASE_URL,
    )
