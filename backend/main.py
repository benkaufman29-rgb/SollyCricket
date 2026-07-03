"""
Solly Cricket — FastAPI backend for LLM-powered commentary.

Single endpoint: POST /commentary
Accepts match outcome + context, builds a prompt, calls OpenRouter,
and returns the commentary text.

Deploy on Render with OPENROUTER_API_KEY set as an environment variable.
"""

import logging
import os
import random
import re
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

# ---------------------------------------------------------------------------
# Logging — Render captures stdout
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("solly-backend")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Solly Cricket Commentary API")

# Allow all origins — the desktop app's webview makes requests from a local
# file:// origin. In production this is not a security concern because the
# API key is server-side and the endpoint is a public proxy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CommentaryRequest(BaseModel):
    # Primary: send a pre-built prompt (current desktop client path)
    prompt: str | None = None
    # Future: send raw outcome + context for server-side prompt building
    outcome: dict | None = None
    context: dict | None = None


class CommentaryResponse(BaseModel):
    commentary: str | None
    error: str | None = None

# ---------------------------------------------------------------------------
# Prompt building (ported from engine/commentary_llm.py)
# ---------------------------------------------------------------------------

def build_prompt(outcome: dict, context: dict) -> str:
    """Build a concise prompt for the LLM based on the ball outcome."""
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
            pos = count - i
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
# OpenRouter caller (ported from engine/commentary_llm.py)
# ---------------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PREFERRED_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "openrouter/free",
]


def _is_valid_commentary(text: str) -> bool:
    """Return True if the LLM output looks like a real cricket commentary sentence."""
    if not text or len(text) < 8:
        return False

    raw = text.strip()

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

    meta_phrases = [
        "word count", "max 20", "20 words", "short sentence", "lively sentence",
        "output only", "just the sentence", "commentary sentence",
    ]
    for phrase in meta_phrases:
        if phrase in lower:
            return False

    if raw.startswith("```") or raw.startswith("{"):
        return False

    if len(raw.split()) <= 2:
        return False

    safety_phrases = [
        "i cannot provide", "i can't provide", "as an ai",
        "remember that", "always consult", "it's important to",
    ]
    for phrase in safety_phrases:
        if phrase in lower:
            return False

    return True


def call_openrouter(prompt: str, timeout: float = 15.0) -> str | None:
    """Call OpenRouter API with retry and exponential backoff on rate limits.

    When a 429 (Too Many Requests) is hit:
      - Wait 1s, retry same model
      - Then 2s, retry same model
      - Then 4s, retry same model
      - Then move to next model in the whitelist

    Respects OpenRouter's Retry-After header if present.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY not set")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/solly-cricket",
        "X-Title": "Solly Cricket",
    }

    for model in PREFERRED_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 500,
        }

        # Retry with exponential backoff for this model
        backoff = 1.0
        for attempt in range(4):  # 3 retries + 1 initial
            try:
                resp = requests.post(
                    OPENROUTER_URL, json=payload, headers=headers, timeout=timeout
                )
                if resp.status_code == 429:
                    # Respect Retry-After header, or use exponential backoff
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else backoff
                    logger.info(
                        f"429 rate limited on {model}, retrying in {wait:.0f}s "
                        f"(attempt {attempt + 1}/4)"
                    )
                    time.sleep(wait)
                    backoff = min(backoff * 2, 8.0)  # Cap at 8s
                    continue

                resp.raise_for_status()
                data = resp.json()
                choice = data["choices"][0]["message"]
                text = choice.get("content") or choice.get("reasoning") or ""
                if text.strip():
                    return text.strip()[:150]
                break  # Empty response isn't a retry-able error
            except requests.RequestException as e:
                if attempt < 3:
                    logger.info(f"{model} attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 8.0)
                else:
                    logger.warning(f"Model {model} failed after 4 attempts: {e}")

    logger.error("All OpenRouter models failed")
    return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.post("/commentary", response_model=CommentaryResponse)
def generate_commentary(req: CommentaryRequest):
    """Generate commentary for a ball outcome via OpenRouter.

    Accepts either:
    1. A pre-built `prompt` string (current desktop client)
    2. `outcome` + `context` dicts (for future server-side prompt control)

    Falls back to a template if all API calls fail.
    """
    # Resolve the prompt
    if req.prompt:
        prompt = req.prompt
    elif req.outcome and req.context:
        prompt = build_prompt(req.outcome, req.context)
    else:
        return CommentaryResponse(commentary=None, error="Need 'prompt' or 'outcome'+'context'")

    llm_text = call_openrouter(prompt)

    if llm_text and not _is_valid_commentary(llm_text):
        logger.info("Invalid LLM response, retrying...")
        llm_text = call_openrouter(prompt)

    if llm_text and _is_valid_commentary(llm_text):
        return CommentaryResponse(commentary=llm_text.strip())

    # Last resort: a simple template fallback on the server side.
    # The desktop app also has its own template fallback, but this
    # ensures we always return something even if the desktop doesn't.
    template = _template_fallback(req.outcome)
    return CommentaryResponse(commentary=template, error="LLM unavailable, used template")


def _template_fallback(outcome: dict) -> str:
    """Simple server-side template fallback."""
    COMM_TEMPLATES = {
        "dot": ["{batsman} defends solidly back to {bowler}."],
        "one": ["{batsman} nudges it for a single."],
        "two": ["{batsman} works it into the gap and comes back for two."],
        "three": ["{batsman} pushes it through the covers for three."],
        "four": ["FOUR! {batsman} cracks it through the covers!"],
        "six": ["SIX! {batsman} launches it over the ropes!"],
        "wicket_bowled": ["{batsman} is bowled! {bowler} strikes!"],
        "wicket_caught": ["{batsman} is caught! {fielder} takes a clean catch off {bowler}."],
        "wicket_lbw": ["{batsman} is LBW! {bowler} traps him in front."],
        "wicket_runout": ["Run out! {batsman} is short of his crease."],
        "wicket_stumped": ["Stumped! {batsman} is out of his crease."],
        "wide": ["Wide from {bowler}."],
        "noball": ["No-ball from {bowler}."],
        "bye": ["Byes taken."],
        "legbye": ["Leg-byes."],
    }

    if outcome["is_wicket"]:
        key = f"wicket_{outcome['wicket_type']}"
        templates = COMM_TEMPLATES.get(key, COMM_TEMPLATES["wicket_bowled"])
        return random.choice(templates).format(
            batsman=outcome.get("dismissed_batsman_name", outcome["batsman_name"]),
            bowler=outcome["bowler_name"],
            fielder=outcome.get("fielder", "a fielder"),
        )
    elif outcome["extra_type"]:
        if outcome["extra_type"] in ("w",):
            return random.choice(COMM_TEMPLATES["wide"]).format(bowler=outcome["bowler_name"])
        elif outcome["extra_type"] == "nb":
            return random.choice(COMM_TEMPLATES["noball"]).format(bowler=outcome["bowler_name"])
        else:
            key = "bye" if outcome["extra_type"] == "b" else "legbye"
            return random.choice(COMM_TEMPLATES[key])
    else:
        runs_map = {0: "dot", 1: "one", 2: "two", 3: "three", 4: "four", 6: "six"}
        key = runs_map.get(outcome["runs"], "dot")
        return random.choice(COMM_TEMPLATES[key]).format(
            batsman=outcome["batsman_name"],
            bowler=outcome["bowler_name"],
        )


# ---------------------------------------------------------------------------
# Health check (useful for Render monitoring and cold-start detection)
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Direct execution (for local testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)