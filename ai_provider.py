"""
AI summarization provider with an automatic fallback chain.

Order: Gemini -> Grok -> OpenRouter.
If a provider is rate-limited, errors out, or is missing an API key, the
next provider in the chain is tried transparently. The end user only ever
sees the final summary (or a single friendly error if every provider
fails) and is never shown which provider actually produced it.

The summarization prompt itself is intentionally left untouched from the
original implementation.
"""

import logging

import google.generativeai as genai
import requests

import config

logger = logging.getLogger(__name__)

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

_gemini_model = None


def _get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        _gemini_model = genai.GenerativeModel(config.GEMINI_MODEL)
    return _gemini_model


def build_summary_prompt(messages: list[str]) -> str:
    """Build the summarization prompt. Kept identical to the original bot."""
    prompt = """تو یک دستیار صمیمی و خودمونی هستی. مکالمه زیر رو بخون و خیلی روان و عامیانه، در قالب یک پاراگراف کوتاه بگو بچه‌ها داشتن در مورد چی حرف می‌زدن.
    بسیار مهم: ساعت پیام‌ها (که در براکت نوشته شده) صرفاً برای اینه که خودت فواصل زمانی و گپ‌های گفتگو رو درک کنی. به هیچ وجه و تحت هیچ شرایطی نباید خودِ ساعت‌ها یا عباراتی مثل "فلانی در ساعت فلان گفت" رو توی متن خلاصه‌ی نهایی بنویسی! فقط از زمان‌ها کمک بگیر تا بفهمی بحث کی عوض شده و اون رو به شکل یک داستان طبیعی نقل کن.
    فقط لپ کلام رو بگو. اصلاً از لیست، تیتربندی و عباراتی مثل 'نکات کلیدی' استفاده نکن. حتما ذکر کن چه کسی چه حرفی رو زده. اسم هاشون رو هم اگه انگلیسی بود به فارسی تبدیل کن تو پیام.

    متن پیام‌ها:
    """

    for msg in messages:
        prompt += f"{msg}\n"

    return prompt


def _clean_response_text(raw_text: str) -> str:
    return raw_text.replace("*", "").replace("#", "").strip()


def _try_gemini(prompt: str) -> str:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Gemini API key is not configured")
    model = _get_gemini_model()
    response = model.generate_content(prompt)
    return _clean_response_text(response.text)


def _try_openai_compatible(base_url: str, api_key: str, model: str, prompt: str) -> str:
    """Shared caller for Grok and OpenRouter, both of which expose an
    OpenAI-compatible /chat/completions endpoint."""
    if not api_key:
        raise RuntimeError("API key is not configured")

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=config.AI_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["choices"][0]["message"]["content"]
    return _clean_response_text(raw_text)


def _try_grok(prompt: str) -> str:
    return _try_openai_compatible(
        config.GROK_BASE_URL, config.GROK_API_KEY, config.GROK_MODEL, prompt
    )


def _try_openrouter(prompt: str) -> str:
    return _try_openai_compatible(
        config.OPENROUTER_BASE_URL, config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL, prompt
    )


# Order matters: this is the exact fallback chain requested.
_PROVIDERS = (
    ("gemini", _try_gemini),
    ("grok", _try_grok),
    ("openrouter", _try_openrouter),
)


def generate_summary(prompt: str) -> str:
    """Run the prompt through each provider in order until one succeeds.

    Raises RuntimeError if every provider fails.
    """
    last_error = None
    for provider_name, provider_call in _PROVIDERS:
        try:
            return provider_call(prompt)
        except Exception as error:
            logger.warning("AI provider '%s' failed, trying next one: %s", provider_name, error)
            last_error = error

    raise RuntimeError("All AI providers failed") from last_error
