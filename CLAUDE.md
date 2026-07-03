# SollyCricket — Project Documentation

## Overview
A desktop cricket simulation game with an ESPNcricinfo-style UI. Built with Python (`pywebview`) for the engine and HTML/CSS/JS for the frontend. Packaged as a standalone Windows executable. LLM commentary is powered by a FastAPI backend on Render, keeping the API key server-side.

## Current State (July 2026)
Everything is implemented and working:
- **Match engine** with ball-by-ball simulation, wickets, extras, strike rotation
- **Commentary system** with template mode (always) + optional LLM mode via FastAPI backend
- **Desktop GUI** with a 50/50 split layout:
  - Left half: Batting scorecard → Bowling scorecard → Condensed Fall of Wickets
  - Right half: Scrollable commentary feed (newest first)
- **Controls**: Bowl Ball, Autoplay, Start 2nd Innings, Reset Match
- **Pre‑loaded squads**: Australia and England (Ashes)
- **Clean start screen** — no API key input (key lives on Render server)

## Project Structure

```
project-solly-cricket/
├── backend/
│   ├── main.py                   # FastAPI app — POST /commentary, proxies to OpenRouter
│   ├── requirements.txt          # fastapi, uvicorn, requests
│   └── README.md                 # Render deployment instructions
├── engine/
│   ├── models.py                 # Player, Team, BallOutcome, Innings, MatchState
│   ├── simulator.py              # Delivery simulation + get_next_bowler
│   ├── commentary_templates.py   # Shared template data (no circular imports)
│   └── commentary_llm.py         # Multi-provider LLM client + graceful fallback
├── gui/
│   ├── index.html                # Single‑page layout + clean start screen
│   ├── style.css                 # Cricinfo-inspired styling (blue/slate palette)
│   └── app.js                    # UI updates, API bridge calls, autoplay
├── data/squads/
│   ├── australia.json            # Australia squad
│   └── england.json              # England squad
├── main.py                       # (Legacy) terminal‑based TUI using Rich
├── gui_main.py                   # Python entry point — Api class, webview launch
├── assets/
│   └── SC.png                    # Game logo (shown on start screen)
├── requirements.txt              # pywebview, pyinstaller, requests
├── CLAUDE.md                     # This file
├── commentary_config.example.json # Template for API key config file (legacy)
├── tests/
│   ├── __init__.py
│   └── test_engine.py            # Unit tests for match engine
└── dist/
    └── SollyCricket.exe          # Packaged standalone executable
```

## Development Workflow

### 1. Edit source files
- **Python engine**: `engine/models.py`, `engine/simulator.py`, `engine/commentary_llm.py`, `gui_main.py`
- **Frontend**: `gui/index.html`, `gui/style.css`, `gui/app.js`
- **Squad data**: `data/squads/*.json`

### 2. Run in development mode (no rebuild needed)
```bash
python gui_main.py
```
Launches the app window immediately — no PyInstaller required. Useful for rapid iteration on HTML/CSS/JS changes.

### 3. Rebuild the executable
```bash
pyinstaller --onefile --noconsole --name SollyCricket \
    --add-data "data;data" --add-data "gui;gui" --add-data "assets;assets" gui_main.py
```
Output: `dist/SollyCricket.exe`

## Key Implementation Details

### Commentary Generation (Two Modes, Graceful Fallback)

The game supports commentary generation with automatic fallback:

1. **Template mode** (always available): Picks a random template from `engine/commentary_templates.py` and formats in player names. Fast and deterministic. Works fully offline.

2. **LLM mode** (optional): Generates varied, context-aware commentary via a FastAPI backend on Render. **No local model downloads, no API key on the client.** If the backend call fails (cold start, network error, rate limit), it falls back silently to templates.

**Primary path (auto-detected, no config needed):**

| Provider | How it works | Notes |
|---|---|---|
| **solly_backend** | Desktop sends prompt to `https://solly-cricket-api.onrender.com/commentary` → backend calls OpenRouter with server-side key | Auto-selected by default. Override URL via `SOLLY_BACKEND_URL` env var. |

**Legacy providers (fallback, require env var set):**

| # | Provider | Key env var | Free tier | Notes |
|---|---|---|---|---|
| 1 | **OpenRouter** | `OPENROUTER_API_KEY` | Yes | Direct client-side call (for dev) |
| 2 | **Gemini** | `GEMINI_API_KEY` | 60 req/min | Google's flash model |
| 3 | **Groq** | `GROQ_API_KEY` | 30 req/min | Llama 3.1 8B on fast LPUs |
| 4 | **OpenAI** | `OPENAI_API_KEY` | No | GPT-4o-mini (~$0.001/match) |
| 5 | **Ollama** | None (local) | Yes | Requires Ollama installed & running |

### Render Backend (`backend/main.py`)

Single FastAPI endpoint `POST /commentary` deployed on Render:
- Accepts `{"prompt": "..."}` (pre-built prompt from desktop) or `{"outcome": ..., "context": ...}` (for server-side prompt building)
- Holds `OPENROUTER_API_KEY` as a Render environment variable
- Retries with exponential backoff (1s → 2s, jittered) on 429 rate limits
- Falls back to a server-side template if all models fail
- Health check at `GET /health`
- Model whitelist (server-side): `google/gemma-4-26b-a4b-it:free` → `google/gemma-4-31b-it:free` → `openrouter/free`

### Render Free Tier Notes
- Spins down after 15 min of inactivity (~30s cold start on next request)
- The desktop's 20s timeout may cause the first ball after idle to use template commentary; subsequent balls hit the warm backend
- Paid plan ($7/mo) eliminates cold starts

### Accurate Post-Delivery Context

The LLM receives the **actual post-delivery** match state, not the pre-delivery snapshot. Flow in `step_ball()`:
1. Simulate delivery (template commentary, fast)
2. Update match state (`self.match.step_ball(outcome)`)
3. Generate LLM commentary using the **updated** innings state (correct score, wickets, over)
4. Replace `outcome.description` with the LLM text before serializing to JSON

This means the commentary always reflects the true match state after the ball was bowled.

### Autoplay Chaining

Autoplay uses recursive `setTimeout` instead of `setInterval`:
- Each ball waits for the previous `step_ball()` promise to resolve before scheduling the next
- Prevents request pile-up when LLM calls take variable time (1–8 seconds)
- Still maintains ~1200ms gap between ball completions

### Frontend ↔ Backend bridge
- `gui_main.py` defines an `Api` class exposed to JavaScript via pywebview.
- `app.js` calls `pywebview.api.get_state()`, `.step_ball()`, `.reset_match()`, `.start_second_innings()`, `.get_commentary_status()`.
- Each call returns a JSON state object that `updateUI()` renders into the DOM.

### Data flow
1. User clicks "Bowl Ball" → JS calls `step_ball()` on the Python API.
2. Python calls `simulate_delivery()`, updates `MatchState`, generates optional LLM commentary with post-delivery context, serialises the full state to JSON.
3. JS receives the response → calls `updateUI(state)` → updates batting table, bowling table, FOW text, and commentary feed.

### Comment format
Commentary displays as `{BOWLER} to {BATTER}` (bowler first) with a coloured bubble indicating the outcome (W for wicket, 4/6 for boundaries, runs number, or extra type).

### BallOutcome model
Extended with:
- `fielder_name` — fielder involved in a wicket (for LLM context)
- `bat_rating` / `bowl_rating` — ratings at time of delivery (for context-aware commentary)

### Conditional button visibility
- "Start 2nd Innings" appears only when innings 1 completes.
- "Bowl Ball" is hidden during innings transitions and at match end.
- Autoplay stops automatically when an innings finishes.

## Important Notes
- Close the running `SollyCricket.exe` before trying to rebuild — PyInstaller locks the output file.
- The `main.py` terminal version is kept for reference but is not the active interface.
- Squad data is bundled inside the executable via `--add-data`, so `data/` and `gui/` paths must stay relative to the source tree.
- The window title is set in `gui_main.py` in the `webview.create_window()` call.
- The Render backend URL defaults to `https://solly-cricket-api.onrender.com` — override via `SOLLY_BACKEND_URL` env var for local dev or custom deployments.
- LLM commentary requires internet access and a running Render backend; template mode works fully offline.
- See `backend/README.md` for detailed Render deployment instructions.