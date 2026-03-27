"""
backend/utils/llm_client.py
============================
Universal LLM caller with simple sequential fallback.

Each call_llm invocation independently tries providers in order:
  anthropic → google → openai → openrouter
No shared mutable state between calls — safe for concurrent use.
"""

import asyncio
import json
import re
from typing import Any

import httpx
from loguru import logger

from backend.config import settings

_OPENROUTER_429_RETRIES = 3
_OPENROUTER_429_BACKOFF = 5  # base seconds; capped so HTTP clients/proxies do not hang up
_OPENROUTER_429_BACKOFF_CAP = 35  # max seconds per wait

# OpenAI: skip unusable keys and stop calling after 401 (bad key).
_openai_auth_failed: bool = False
_openai_placeholder_key_logged: bool = False


def _openai_key_usable(key: str) -> bool:
    k = (key or "").strip()
    if len(k) < 8:
        return False
    low = k.lower()
    if low.startswith("sk-your") or "placeholder" in low or low in ("sk-", "test", "xxx"):
        return False
    if k.startswith("your_") or k.startswith("YOUR_"):
        return False
    return True


def _openai_key_ok_for_provider() -> bool:
    global _openai_placeholder_key_logged
    raw = settings.openai_api_key or ""
    if _openai_auth_failed:
        return False
    if not raw.strip():
        return False
    if not _openai_key_usable(raw):
        if not _openai_placeholder_key_logged:
            _openai_placeholder_key_logged = True
            logger.warning(
                "[LLM_CLIENT] OPENAI_API_KEY is set but looks invalid or placeholder — "
                "OpenAI provider skipped (no failed API calls)."
            )
        return False
    return True


def _available_providers() -> list[str]:
    """Return the list of providers that have API keys configured.

    If LLM_PROVIDER=openrouter, OpenRouter is tried first, then other configured
    providers as fallback when OpenRouter is rate-limited or errors.
    """
    preferred = (settings.llm_provider or "").lower().strip()

    def _append_unique(out: list[str], name: str) -> None:
        if name not in out:
            out.append(name)

    out: list[str] = []

    if preferred == "openrouter" and settings.openrouter_api_key:
        _append_unique(out, "openrouter")
    elif preferred == "anthropic" and settings.anthropic_api_key:
        _append_unique(out, "anthropic")
    elif preferred == "google" and (settings.google_api_key or settings.gemini_api_key):
        _append_unique(out, "google")
    elif preferred == "openai" and _openai_key_ok_for_provider():
        _append_unique(out, "openai")

    # Fill remaining configured providers as fallbacks (order: anthropic, google, openai, openrouter).
    if settings.anthropic_api_key:
        _append_unique(out, "anthropic")
    if settings.google_api_key or settings.gemini_api_key:
        _append_unique(out, "google")
    if _openai_key_ok_for_provider():
        _append_unique(out, "openai")
    if settings.openrouter_api_key:
        _append_unique(out, "openrouter")

    return out


async def call_llm(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 1000,
    temperature: float = 0.3,
    expect_json: bool = False,
    strict_json_object: bool = False,
) -> str:
    """
    Try each available provider in order. First success wins.
    Completely stateless — safe for concurrent asyncio.gather calls.
    strict_json_object: when True, OpenAI requests JSON object mode (resume / materials only).
    """
    providers = _available_providers()
    if not providers:
        raise RuntimeError("No LLM providers configured — set at least one API key in .env")

    last_err: Exception | None = None

    for provider in providers:
        logger.debug(f"LLM call → provider={provider} max_tokens={max_tokens}")
        try:
            result = await _dispatch(
                provider, messages, system, max_tokens, temperature, strict_json_object
            )
            if expect_json:
                result = _strip_json_fences(result)
            return result
        except Exception as e:
            last_err = e
            logger.warning(f"[LLM_CLIENT] provider_failed={provider} err={e}")
            continue

    raise last_err or RuntimeError("All LLM providers failed")


def call_llm_sync(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 1000,
    temperature: float = 0.3,
    expect_json: bool = False,
    strict_json_object: bool = False,
) -> str:
    """Synchronous wrapper for non-async contexts."""
    import asyncio
    return asyncio.run(call_llm(messages, system, max_tokens, temperature, expect_json, strict_json_object))


async def _dispatch(
    provider: str, messages, system, max_tokens, temperature, strict_json_object: bool = False
) -> str:
    if provider == "anthropic":
        return await _call_anthropic(messages, system, max_tokens, temperature)
    if provider == "google":
        return await _call_gemini(messages, system, max_tokens, temperature)
    if provider == "openai":
        return await _call_openai(
            messages, system, max_tokens, temperature, strict_json_object=strict_json_object
        )
    if provider == "openrouter":
        return await _call_openrouter(messages, system, max_tokens, temperature)
    raise ValueError(f"Unknown provider: {provider}")


# ── Provider implementations ─────────────────────────────────────────────

async def _call_anthropic(messages, system, max_tokens, temperature) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or "You are a helpful assistant.",
        messages=messages,
    )
    return response.content[0].text


async def _call_gemini(messages, system, max_tokens, temperature) -> str:
    api_key = settings.google_api_key or settings.gemini_api_key
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": f"[System]: {system}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood."}]})
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    model = (settings.google_model or "gemini-2.0-flash").replace("gemini/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            json={
                "contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai(
    messages, system, max_tokens, temperature, *, strict_json_object: bool = False
) -> str:
    global _openai_auth_failed
    all_messages: list[dict[str, Any]] = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    body: dict[str, Any] = {
        "model": settings.openai_model or "gpt-4o-mini",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": all_messages,
    }
    if strict_json_object:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if r.status_code == 401:
        if not _openai_auth_failed:
            logger.error(
                "[LLM_CLIENT] OpenAI returned 401 — OPENAI_API_KEY is missing or invalid. "
                "Disabling OpenAI for this process; fix the key or unset it to avoid noisy retries."
            )
        _openai_auth_failed = True
        raise RuntimeError("OpenAI authentication failed (401)")
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


async def _call_openrouter(messages, system, max_tokens, temperature) -> str:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    models_to_try: list[str] = []
    if settings.openrouter_model:
        models_to_try.append(settings.openrouter_model)
    if getattr(settings, "openrouter_fallback_model", ""):
        models_to_try.append(settings.openrouter_fallback_model)

    if not models_to_try:
        raise RuntimeError("No OpenRouter models configured")

    last_err: Exception | None = None
    for model in models_to_try:
        for attempt in range(_OPENROUTER_429_RETRIES):
            try:
                content = await _openrouter_single_call(
                    model, all_messages, max_tokens, temperature
                )
                return content
            except _RateLimitError as e:
                wait = min(
                    _OPENROUTER_429_BACKOFF * (attempt + 1),
                    _OPENROUTER_429_BACKOFF_CAP,
                )
                logger.warning(
                    f"[LLM_CLIENT] 429 on {model} (attempt {attempt + 1}/"
                    f"{_OPENROUTER_429_RETRIES}), retrying in {wait}s"
                )
                last_err = e
                await asyncio.sleep(wait)
            except Exception as e:
                last_err = e
                logger.warning(f"[LLM_CLIENT] openrouter_model_failed={model} err={e}")
                break  # non-retryable error → try next model

    raise last_err or RuntimeError("OpenRouter call failed for all models")


class _RateLimitError(RuntimeError):
    """Raised on 429 to trigger retry."""


async def _openrouter_single_call(
    model: str, all_messages: list, max_tokens: int, temperature: float
) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/jonathanrao99/job-agent",
                "X-Title": "Job Search Agent",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": all_messages,
            },
        )

    data: dict[str, Any] | None = None
    try:
        data = r.json()
    except Exception:
        data = None

    if r.status_code == 429:
        msg = "rate limited"
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            msg = data["error"].get("message") or msg
        raise _RateLimitError(f"OpenRouter 429: {msg}")

    if r.status_code >= 400:
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = data["error"]
            msg = err.get("message") or str(err)
            code = err.get("code")
            raise RuntimeError(
                f"OpenRouter error: {msg}" + (f" (code={code})" if code else "")
            )
        raise RuntimeError(f"OpenRouter HTTP {r.status_code}")

    if not isinstance(data, dict):
        snippet = (r.text or "")[:240].replace("\n", " ")
        raise RuntimeError(
            f"OpenRouter returned non-JSON (HTTP {r.status_code}): {snippet or 'empty body'}"
        )

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {list(data.keys())}")

    msg_obj = choices[0].get("message") or {}
    content = msg_obj.get("content")

    # Many free models are reasoning-only: content is null, answer is in reasoning.
    if content is None:
        content = _extract_from_reasoning(msg_obj)

    if content is None:
        content = choices[0].get("text")

    if content is None:
        raise RuntimeError("OpenRouter returned empty content")

    return str(content)


def _extract_from_reasoning(msg: dict) -> str | None:
    """Pull usable text from reasoning_details when content is null."""
    details = msg.get("reasoning_details") or []
    reasoning_text = msg.get("reasoning") or ""

    if details:
        parts = [d.get("text", "") for d in details if isinstance(d, dict)]
        reasoning_text = "".join(parts)

    if not reasoning_text:
        return None

    # Reasoning models wrap thinking in <think>...</think> then produce the answer.
    # Try to extract text after </think>.
    after_think = re.split(r"</think>", reasoning_text, maxsplit=1)
    if len(after_think) == 2 and after_think[1].strip():
        return after_think[1].strip()

    # If no </think> tag, the whole reasoning might contain the JSON answer.
    # Look for a JSON object in the reasoning.
    json_match = re.search(r"\{[\s\S]*\}", reasoning_text)
    if json_match:
        return json_match.group(0)

    arr_match = re.search(r"\[[\s\S]*\]", reasoning_text)
    if arr_match:
        return arr_match.group(0)

    return None


# ── Helpers ──────────────────────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines).strip()
    return text


def parse_json_response(text: str) -> dict | list:
    clean = _strip_json_fences(text)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        # Common failure mode: models return JSON with unescaped newlines inside strings.
        try:
            extracted = _extract_json_object(clean)
            repaired = _escape_newlines_in_json_strings(extracted)
            return json.loads(repaired)
        except Exception:
            pass
        try:
            extracted = _extract_json_array(clean)
            repaired = _escape_newlines_in_json_strings(extracted)
            return json.loads(repaired)
        except Exception:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Raw response: {text[:500]}")
            raise ValueError(f"LLM returned invalid JSON: {e}") from e


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _extract_json_array(text: str) -> str:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _escape_newlines_in_json_strings(text: str) -> str:
    """
    JSON strings cannot contain raw newline characters.
    If an LLM outputs multi-line JSON strings, json.loads will fail.
    This function escapes raw '\\n' characters inside quoted strings.
    """
    out: list[str] = []
    in_str = False
    escape = False

    for ch in text:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                # Drop CR to avoid odd formatting.
                continue
            out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_str = True

    return "".join(out)
