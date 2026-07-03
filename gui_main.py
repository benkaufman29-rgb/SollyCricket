import base64
import json
import os
import sys
import webview
from engine.models import MatchState, Team
from engine.simulator import simulate_delivery, get_next_bowler
from engine.commentary_llm import get_active_provider_name, list_available_providers, generate_commentary

def get_asset_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class Api:
    def __init__(self):
        self.match = None
        self.aus_team = None
        self.eng_team = None
        self._innings1_snapshot = None  # Saved after innings 1 completes, before stats are wiped
        self.load_squads()
        self.init_match()

    def set_api_key(self, key: str) -> dict:
        """(Deprecated) API key input removed — use SOLLY_BACKEND_URL env var instead."""
        return {"status": "ok"}

    def get_commentary_status(self) -> dict:
        """Report which commentary provider is active."""
        provider = get_active_provider_name()
        return {
            "provider": provider,
            "llm_active": provider is not None,
        }

    def load_squads(self):
        aus_path = get_asset_path(os.path.join("data", "squads", "australia.json"))
        eng_path = get_asset_path(os.path.join("data", "squads", "england.json"))
        self.aus_team = Team.from_json_file(aus_path)
        self.eng_team = Team.from_json_file(eng_path)

    def init_match(self):
        # Default to a 20-over match
        self.match = MatchState(self.aus_team, self.eng_team, overs_limit=20)
        self.match.start_match()
        self._innings1_snapshot = None

    def serialize_player(self, player):
        if not player:
            return None
        return {
            "name": player.name,
            "role": player.role,
            "batting_hand": player.batting_hand,
            "bowling_type": player.bowling_type,
            "batting_order": player.batting_order,
            "runs_scored": player.runs_scored,
            "balls_faced": player.balls_faced,
            "fours": player.fours,
            "sixes": player.sixes,
            "dismissal": player.dismissal,
            "dismissal_description": player.dismissal_description,
            "status": player.status,
            "balls_bowled": player.balls_bowled,
            "runs_conceded": player.runs_conceded,
            "wickets_taken": player.wickets_taken,
            "maidens": player.maidens,
            "overs_bowled": player.overs_bowled,
            "strike_rate": player.strike_rate,
            "economy_rate": player.economy_rate
        }

    def serialize_innings(self, innings):
        if not innings:
            return None
        # For innings 1, return the snapshot if available (stats were wiped by innings 2 init)
        if innings == self.match.innings1 and self._innings1_snapshot is not None:
            return self._innings1_snapshot
        return {
            "batting_team_name": innings.batting_team.name,
            "bowling_team_name": innings.bowling_team.name,
            "score": innings.score,
            "wickets": innings.wickets,
            "balls_bowled": innings.balls_bowled,
            "overs_str": innings.overs_str,
            "extras": innings.extras,
            "total_extras": innings.total_extras,
            "is_completed": innings.is_completed,
            "target": innings.target,
            "striker": self.serialize_player(innings.striker),
            "non_striker": self.serialize_player(innings.non_striker),
            "current_bowler": self.serialize_player(innings.current_bowler),
            "batting_card": [self.serialize_player(p) for p in innings.batting_team.players],
            "bowling_card": [self.serialize_player(p) for p in innings.bowling_team.players if p.balls_bowled > 0 or p == innings.current_bowler],
            "fall_of_wickets": innings.fall_of_wickets,
            "commentary": [
                {
                    "runs": b.runs,
                    "extras": b.extras,
                    "extra_type": b.extra_type,
                    "is_wicket": b.is_wicket,
                    "wicket_type": b.wicket_type,
                    "batsman_name": b.batsman_name,
                    "bowler_name": b.bowler_name,
                    "dismissed_batsman_name": b.dismissed_batsman_name,
                    "fielder_name": b.fielder_name,
                    "description": b.description,
                    "dismissal_mode": b.dismissal_mode
                } for b in innings.commentary  # Send all deliveries
            ]
        }

    def get_state(self):
        """Returns the serialized match state."""
        return {
            "team1_name": self.match.team1.name,
            "team2_name": self.match.team2.name,
            "innings_number": self.match.innings_number,
            "status_message": self.match.status_message,
            "innings1": self.serialize_innings(self.match.innings1),
            "innings2": self.serialize_innings(self.match.innings2),
            "overs_limit": self.match.overs_limit
        }

    def step_ball(self):
        """Simulates one delivery and returns the updated state.

        The LLM commentary call runs synchronously so the response
        always has correct, timely commentary. Autoplay chains via
        promise so calls never pile up.
        """
        if self.match.current_innings.is_completed:
            return self.get_state()

        innings = self.match.current_innings

        # Check for over transition
        if innings.balls_bowled > 0 and innings.balls_bowled % 6 == 0 and innings.current_bowler.current_over_balls == 0:
            next_bowler = get_next_bowler(innings.batting_team, innings.bowling_team, innings.current_bowler)
            innings.change_bowler(next_bowler)

        # 1. Simulate delivery (fast — template commentary)
        outcome = simulate_delivery(
            innings.batting_team,
            innings.bowling_team,
            innings.striker,
            innings.non_striker,
            innings.current_bowler,
        )

        # 2. Update match state first (so context reflects post-delivery reality)
        self.match.step_ball(outcome)

        # 3. Generate LLM commentary with ACCURATE post-delivery context
        innings = self.match.current_innings

        # --- Find the batsman who faced this ball to get their individual score ---
        batsman_player = None
        for p in innings.batting_team.players:
            if p.name == outcome.batsman_name:
                batsman_player = p
                break
        batsman_runs = batsman_player.runs_scored if batsman_player else 0
        batsman_balls = batsman_player.balls_faced if batsman_player else 0

        # --- Collect the last 6 deliveries' commentary for context ---
        # The current delivery is at the end of commentary list (just appended by step_ball).
        # Take up to 6 descriptions before it.
        prev = innings.commentary[:-1]  # all except current
        recent_descriptions = [b.description for b in prev[-6:]]

        llm_text = generate_commentary(
            {
                "runs": outcome.runs,
                "extras": outcome.extras,
                "extra_type": outcome.extra_type,
                "is_wicket": outcome.is_wicket,
                "wicket_type": outcome.wicket_type,
                "batsman_name": outcome.batsman_name,
                "bowler_name": outcome.bowler_name,
                "dismissed_batsman_name": outcome.dismissed_batsman_name,
                "fielder": outcome.fielder_name,
            },
            {
                "score": innings.score,
                "wickets": innings.wickets,
                "over_str": innings.overs_str,
                "bat_rating": outcome.bat_rating,
                "bowl_rating": outcome.bowl_rating,
                "batsman_runs": batsman_runs,
                "batsman_balls": batsman_balls,
                "recent_commentary": recent_descriptions,
            },
        )
        if llm_text:
            outcome.description = llm_text

        return self.get_state()

    def start_second_innings(self):
        """Transitions to the second innings."""
        if self.match.innings_number == 1 and self.match.innings1.is_completed:
            # Snapshot innings 1 stats BEFORE they get wiped by start_second_innings
            self._innings1_snapshot = self.serialize_innings(self.match.innings1)
            self.match.start_second_innings()
        return self.get_state()

    def reset_match(self):
        """Resets the match."""
        self.init_match()
        return self.get_state()

    def get_logo(self):
        """Returns the SC.png logo as a base64 data URI."""
        logo_path = get_asset_path("assets/SC.png")
        try:
            with open(logo_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{data}"
        except FileNotFoundError:
            return ""


def main():
    api = Api()

    # Report commentary mode
    provider = get_active_provider_name()
    if provider:
        print(f"  Commentary: LLM ({provider}) — generating varied commentary via API")
    else:
        print("  Commentary: templates — for LLM-powered commentary:")
        print("              Set SOLLY_BACKEND_URL env var pointing to your")
        print("              FastAPI backend on Render (see backend/README.md)")

    # Load index.html
    html_path = get_asset_path(os.path.join("gui", "index.html"))
    
    # Create window
    webview.create_window(
        title="Solly Cricket",
        url=html_path,
        js_api=api,
        width=1200,
        height=800,
        resizable=True
    )
    
    # Start webview
    webview.start()

if __name__ == "__main__":
    main()
