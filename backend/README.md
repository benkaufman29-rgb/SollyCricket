# Solly Cricket — FastAPI Backend

A thin FastAPI backend that proxies commentary requests to OpenRouter. The
API key stays server-side — never embedded in the desktop app.

## Deploy on Render

### 1. Push to GitHub

Make sure the whole project (including the `backend/` folder) is pushed to a
GitHub repository.

### 2. Create a Web Service

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. **Connect your GitHub repo** and select it
4. Configure:

   | Field | Value |
   |---|---|
   | **Name** | `solly-cricket-api` |
   | **Region** | Choose closest to you (e.g. `Frankfurt` or `Oregon`) |
   | **Branch** | `main` (or your branch) |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r backend/requirements.txt` |
   | **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
   | **Plan** | **Free** |

5. Under **Environment Variables**, add:

   - **Key:** `OPENROUTER_API_KEY`
   - **Value:** `sk-or-v1-...` (your actual OpenRouter API key)

6. Click **Deploy Web Service**

Render builds and starts the service (~2–3 minutes). You'll see logs in the dashboard.

### 3. Copy your URL

Once deployed, Render shows your URL — something like:

```
https://solly-cricket-api.onrender.com
```

### 4. Configure the Desktop App

Set the environment variable before launching:

```bash
export SOLLY_BACKEND_URL=https://solly-cricket-api.onrender.com
python gui_main.py
```

Or set it permanently in your shell profile (`~/.bashrc`, `~/.zshrc`, etc.).

## Local Development

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run (with your OpenRouter key)
export OPENROUTER_API_KEY=sk-or-v1-...
uvicorn backend.main:app --reload --port 8000

# Test
curl -X POST http://localhost:8000/commentary \
  -H "Content-Type: application/json" \
  -d '{"outcome": {"runs": 4, "is_wicket": false, "batsman_name": "Head", "bowler_name": "Wood"}, "context": {"score": 45, "wickets": 2, "over_str": "8.3"}}'
```

## Free Tier Notes

- Render's free tier **spins down after 15 minutes of inactivity**.
- The first request after idle triggers a ~30s **cold start**.
- The desktop app uses a 15s timeout; if the backend is cold, that ball
  uses template commentary instead. Subsequent balls hit the warm backend.
- If cold starts are annoying, **upgrade to Render's $7/month plan** — no
  cold starts, consistent <1s response.
- Free tier gives 750 hours/month (one service 24/7 uses ~744 hours).