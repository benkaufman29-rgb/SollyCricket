"""
LLM-powered commentary generator — cloud API providers.

Supports multiple backends with graceful fallback to templates.
No local model downloads required.

API keys are resolved from (highest priority first):
  1. Environment variable
  2. A `commentary_config.json` file alongside the game
     (format: {"openrouter_api_key": "sk-or-v1-...", "gemini_api_key": "..."})
"""

import json
import os
import random
import logging
from engine.commentary_templates import COMMENTARY_TEMPLATES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config file helper
# ---------------------------------------------------------------------------

def _find_config_file() -> dict:
    """Look for commentary_config.json in the game directory."""
    # Check next to the script, and next to the potential .exe
    search_dirs = [
        os.path.dirname(os.path.abspath(__file__)),       # engine/
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # project root
        os.getcwd(),
    ]
    for d in search_dirs:
        path = os.path.join(d, "commentary_config.json")
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


_CONFIG_CACHE = {}


def _get_key(name: str) -> str | None:
    """Resolve an API key: env var first, then config file."""
    # 1. Environment variable
    val = os.environ.get(name)
    if val:
        return val

    # 2. Config file
    if not _CONFIG_CACHE:
        _CONFIG_CACHE.update(_find_config_file())
    # Map env var name to config key (lowercase)
    config_key = name.lower()
    return _CONFIG_CACHE.get(config_key)


# ---------------------------------------------------------------------------
# Provider configs
# ---------------------------------------------------------------------------

# Default Render backend URL — override via SOLLY_BACKEND_URL env var
_DEFAULT_BACKEND_URL = "https://solly-cricket-api.onrender.com"

PROVIDERS = {
    "solly_backend": {
        "env_key": "SOLLY_BACKEND_URL",
        "url": _DEFAULT_BACKEND_URL,
        "free_tier": True,
        "needs_key": False,  # Always available — uses hardcoded default URL
    },
    "openrouter": {
        "env_key": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "openrouter/free",
        "preferred_models": [
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-31b-it:free",
            "openrouter/free",
        ],
        "free_tier": True,
        "needs_key": True,
    },
    "gemini": {
        "env_key": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        "model": "gemini-2.0-flash",
        "free_tier": True,
        "needs_key": True,
    },
    "groq": {
        "env_key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama3-8b-8192",
        "free_tier": True,
        "needs_key": True,
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "free_tier": False,
        "needs_key": True,
    },
    "ollama": {
        "env_key": None,
        "url": "http://localhost:11434/api/generate",
        "model": "llama3.2:3b",
        "free_tier": True,
        "needs_key": False,
    },
}

# Default provider — switch by changing this, or set COMMENTARY_PROVIDER env var
_DEFAULT_PROVIDER = "solly_backend"

# Cache the active provider after first probe
_active_provider = None


def _get_active_provider() -> str | None:
    """Return the name of the first available provider, probing in priority order."""
    global _active_provider
    if _active_provider:
        return _active_provider

    # User override via env var
    preferred = os.environ.get("COMMENTARY_PROVIDER", _DEFAULT_PROVIDER).lower()
    if preferred in PROVIDERS:
        cfg = PROVIDERS[preferred]
        if not cfg["needs_key"] or _get_key(cfg["env_key"]):
            _active_provider = preferred
            return _active_provider

    # Auto-probe: prefer configured cloud providers over unverified local ones
    for name, cfg in PROVIDERS.items():
        if cfg["needs_key"] and _get_key(cfg["env_key"]):
            _active_provider = name
            return _active_provider

    # No cloud key found — try Ollama (keyless) only if it's actually reachable
    if _ping_ollama():
        _active_provider = "ollama"
        return _active_provider

    return None


def _build_prompt(outcome: dict, context: dict) -> str:
    """Build a concise prompt for the LLM based on the ball outcome.

    Uses a system/user format that works well with both small and large models.
    """
    # Build the event description
    if outcome["is_wicket"]:
        wt = outcome["wicket_type"]
        event = f"WICKET — {wt.upper()}, {outcome['dismissed_batsman_name']} out"
        if wt in ("caught", "runout", "stumped"):
            event += f", caught by {outcome.get('fielder', 'a fielder')}"
        event += f", bowler {outcome['bowler_name']}"
    elif outcome["extra_type"]:
        et = {"w": "Wide", "nb": "No-ball", "b": "Byes", "lb": "Leg-byes"}.get(
            outcome["extra_type"], outcome["extra_type"]
        )
        event = f"{et} — {outcome['extras']} extra run(s)"
        event += f", bowler {outcome['bowler_name']}, batsman {outcome['batsman_name']}"
    else:
        runs = outcome["runs"]
        if runs == 0:
            label = "Dot ball"
        elif runs == 4:
            label = "BOUNDARY 4 runs"
        elif runs == 6:
            label = "SIX 6 runs"
        else:
            label = f"{runs} runs"
        event = f"{label} — {outcome['batsman_name']} facing {outcome['bowler_name']}"

    # --- Build rich context string ---
    parts = [f"Score {context['score']}/{context['wickets']}, Over {context['over_str']}"]

    # Batsman's individual score (post-delivery)
    batsman_runs = context.get("batsman_runs")
    batsman_balls = context.get("batsman_balls")
    if batsman_runs is not None:
        star = "" if outcome.get("is_wicket") else "*"
        parts.append(f"{outcome['batsman_name']} on {batsman_runs}{star} ({batsman_balls} balls)")

    # Recent deliveries context (numbered, newest-first)
    recent = context.get("recent_commentary", [])
    if recent:
        labels = []
        count = len(recent)
        for i, desc in enumerate(recent):
            pos = count - i  # 1 = most recent
            if pos == 1:
                label = "Previous ball"
            else:
                label = f"{pos} balls ago"
            labels.append(f"{label}: {desc}")
        parts.append("Earlier — " + " | ".join(labels))

    context_str = ". ".join(parts)

    variation_instruction = ""
    if recent:
        variation_instruction = (
            "Vary your wording — do NOT reuse phrases, adjectives, or "
            "descriptions from the earlier commentary listed above.\n"
        )

    prompt = (
        "You are a cricket commentator. "
        "Reply with ONE short, lively sentence (max 20 words) describing this delivery. "
        f"Delivery: {event}. "
        f"Match context: {context_str}.\n\n"
        f"{variation_instruction}"
        "CRITICAL: Output ONLY the commentary sentence. NO word count, NO reasoning, "
        "NO labels like 'Commentary:', NO meta-text, NO safety disclaimers. "
        "Just the sentence itself."
    )

    return prompt


# ---------------------------------------------------------------------------
# Provider-specific request builders and response parsers
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str, timeout: float = 3.0) -> str | None:
    """Call Gemini 2.0 Flash API."""
    import requests
    api_key = _get_key("GEMINI_API_KEY")
    if not api_key:
        return None
    url = PROVIDERS["gemini"]["url"].replace("{key}", api_key).replace("{model}", PROVIDERS["gemini"]["model"])
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 60,
            "stopSequences": ["\n"],
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text.strip()
    except Exception as e:
        logger.debug(f"Gemini API error: {e}")
    return None


def _call_groq(prompt: str, timeout: float = 3.0) -> str | None:
    """Call Groq (OpenAI-compatible) API."""
    import requests
    api_key = _get_key("GROQ_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": PROVIDERS["groq"]["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 60,
        "stop": ["\n"],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(PROVIDERS["groq"]["url"], json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"Groq API error: {e}")
    return None


def _call_openrouter(prompt: str, timeout: float = 10.0) -> str | None:
    """Call OpenRouter API (OpenAI-compatible, routes to free models).

    OpenRouter's free tier often uses reasoning models (GPT-5.5, Nemotron, etc.)
    that need more tokens for reasoning + output. We also handle the case
    where content is in the 'reasoning' field instead of 'content'.
    """
    import requests
    api_key = _get_key("OPENROUTER_API_KEY")
    if not api_key:
        return None

    # Build model list: user config overrides → built-in preferred → fallback
    models = (
        _CONFIG_CACHE.get("openrouter_models", [])
        or PROVIDERS["openrouter"]["preferred_models"]
        or [PROVIDERS["openrouter"]["model"]]
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/solly-cricket",
        "X-Title": "Solly Cricket",
    }

    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 500,
        }
        try:
            resp = requests.post(
                PROVIDERS["openrouter"]["url"],
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]
            # Some reasoning models put content in the 'reasoning' field
            text = choice.get("content") or choice.get("reasoning") or ""
            if text.strip():
                return text.strip()[:150]
        except Exception as e:
            logger.debug(f"OpenRouter model {model} failed: {e}")
            continue  # Try next model in whitelist

    return None


def _call_openai(prompt: str, timeout: float = 3.0) -> str | None:
    """Call OpenAI chat completions API."""
    import requests
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": PROVIDERS["openai"]["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 60,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.post(PROVIDERS["openai"]["url"], json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"OpenAI API error: {e}")
    return None


def _call_ollama(prompt: str, timeout: float = 3.0) -> str | None:
    """Call local Ollama server (no API key needed)."""
    import requests
    payload = {
        "model": PROVIDERS["ollama"]["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.8,
            "max_tokens": 60,
            "stop": ["\n"],
        },
    }
    try:
        resp = requests.post(PROVIDERS["ollama"]["url"], json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        return None


def _ping_ollama() -> bool:
    """Quick check if Ollama server is actually running."""
    import requests
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=1.0)
        return resp.ok
    except Exception:
        return False


def _call_solly_backend(prompt: str, timeout: float = 25.0) -> str | None:
    """Call the Solly Cricket FastAPI backend (deployed on Render).

    The backend holds the OpenRouter API key server-side, so the desktop
    app never touches the key. The prompt is built client-side and sent
    as a string.

    Uses the Render URL from env var SOLLY_BACKEND_URL, falling back to
    the hardcoded default URL if not set.

    Falls back gracefully: returns None on any error, so the caller falls
    through to template or the next available provider.
    """
    import requests
    backend_url = (
        os.environ.get("SOLLY_BACKEND_URL", "").rstrip("/")
        or _DEFAULT_BACKEND_URL
    )

    url = f"{backend_url}/commentary"
    payload = {"prompt": prompt}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("commentary")
        if text:
            return text
    except Exception as e:
        logger.debug(f"Solly backend error: {e}")
    return None


# Map provider names to call functions
_PROVIDER_CALLS = {
    "solly_backend": _call_solly_backend,
    "openrouter": _call_openrouter,
    "gemini": _call_gemini,
    "groq": _call_groq,
    "openai": _call_openai,
    "ollama": _call_ollama,
}


def _query_llm(prompt: str, timeout: float = 25.0) -> str | None:
    """Send prompt to the active provider and return the response text."""
    provider = _get_active_provider()
    if not provider:
        return None
    call_fn = _PROVIDER_CALLS.get(provider)
    if not call_fn:
        return None
    return call_fn(prompt, timeout=timeout)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _is_valid_commentary(text: str) -> bool:
    """Return True if the LLM output looks like a real cricket commentary sentence.

    Rejects:
    - Safety/refusal messages (starts with 'I', 'We', 'Sorry', 'User Safety', ...)
    - Instruction-echoing (mentions word count, max words, etc.)
    - Code fences or raw JSON
    - Too short or too long for a one-sentence commentary
    - Excessively generic boilerplate with no cricket content
    """
    if not text or len(text) < 8:
        return False

    raw = text.strip()

    # --- Block list: patterns that are NEVER valid commentary ---
    block_prefixes = [
        "i", "we", "you", "here", "as an ai", "as a language model", "user safety",
        "sorry", "i cannot", "i can't", "i am unable", "i'm unable",
        "this prompt", "the instruction", "the user asked", "the output should",
        "please note", "important:", "note:",
    ]
    lower = raw.lower()
    for prefix in block_prefixes:
        if lower.startswith(prefix):
            return False

    # --- Reject if it mentions instruction details ---
    meta_phrases = [
        "word count", "max 20", "20 words", "short sentence", "lively sentence",
        "output only", "just the sentence", "commentary sentence",
    ]
    for phrase in meta_phrases:
        if phrase in lower:
            return False

    # --- Reject code fences, JSON, brackets-only text ---
    if raw.startswith("```") or raw.startswith("{"):
        return False

    # --- Reject if it's just a single generic word (not a sentence) ---
    if len(raw.split()) <= 2:
        return False

    # --- Reject if it contains safety-policy boilerplate ---
    safety_phrases = [
        "i cannot provide", "i can't provide", "as an ai",
        "remember that", "always consult", "it's important to",
    ]
    for phrase in safety_phrases:
        if phrase in lower:
            return False

    return True


def generate_commentary(outcome: dict, context: dict) -> str:
    """
    Generate commentary for a ball outcome using the configured LLM provider.
    Falls back gracefully to template-based commentary if no provider is available.

    If the first response is invalid (refusal, meta-text, etc.), tries once more
    with the same prompt before falling back to templates.
    """
    prompt = _build_prompt(outcome, context)
    llm_text = _query_llm(prompt)

    if llm_text and not _is_valid_commentary(llm_text):
        # Retry once with the same original prompt
        logger.debug("Invalid LLM response, retrying...")
        llm_text = _query_llm(prompt, timeout=10.0)

    if llm_text and _is_valid_commentary(llm_text):
        return llm_text.strip()

    # Fallback to template system
    return _template_fallback(outcome)


def _template_fallback(outcome: dict) -> str:
    """Fallback: pick a random template, matching the original engine logic."""
    if outcome["is_wicket"]:
        key = f"wicket_{outcome['wicket_type']}"
        template = random.choice(COMMENTARY_TEMPLATES.get(key, COMMENTARY_TEMPLATES["wicket_bowled"]))
        return template.format(
            batsman=outcome.get("dismissed_batsman_name", outcome["batsman_name"]),
            bowler=outcome["bowler_name"],
            fielder=outcome.get("fielder", "a fielder"),
        )
    elif outcome["extra_type"]:
        if outcome["extra_type"] in ("w",):
            template = random.choice(COMMENTARY_TEMPLATES["wide"])
            return template.format(bowler=outcome["bowler_name"])
        elif outcome["extra_type"] == "nb":
            template = random.choice(COMMENTARY_TEMPLATES["noball"])
            return template.format(bowler=outcome["bowler_name"])
        else:
            key = "bye" if outcome["extra_type"] == "b" else "legbye"
            return random.choice(COMMENTARY_TEMPLATES[key])
    else:
        runs_map = {0: "dot", 1: "one", 2: "two", 3: "three", 4: "four", 6: "six"}
        key = runs_map.get(outcome["runs"], "dot")
        template = random.choice(COMMENTARY_TEMPLATES[key])
        return template.format(
            batsman=outcome["batsman_name"],
            bowler=outcome["bowler_name"],
        )


def get_active_provider_name() -> str | None:
    """Return the name of the provider currently in use, or None."""
    return _get_active_provider()


def set_api_key_runtime(env_var_name: str, value: str) -> None:
    """Set an API key at runtime (from the UI) without restarting.

    Sets the env var, resets the provider cache, and saves a config file
    so the key survives restarts.
    """
    os.environ[env_var_name] = value
    global _active_provider
    _active_provider = None  # Force re-probe on next call


def list_available_providers() -> list[dict]:
    """Return a list of providers that are configured and usable."""
    available = []
    for name, cfg in PROVIDERS.items():
        if not cfg["needs_key"] or _get_key(cfg["env_key"]):
            available.append({"name": name, "free_tier": cfg["free_tier"]})
    return available