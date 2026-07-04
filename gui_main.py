import base64
import json
import os
import sys
import webview
from engine.models import MatchState, Team, Player, BallOutcome
from engine.simulator import simulate_delivery, get_next_bowler
from engine.commentary_llm import get_active_provider_name, list_available_providers, generate_commentary, generate_summary

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

    def get_squad_data(self) -> dict:
        """Returns the default squad data for the team setup page (names + roles only, no stats)."""
        return {
            "teams": [
                {
                    "team_name": self.aus_team.name,
                    "players": [p.to_dict() for p in self.aus_team.players]
                },
                {
                    "team_name": self.eng_team.name,
                    "players": [p.to_dict() for p in self.eng_team.players]
                }
            ]
        }

    def start_with_custom_squads(self, squads_json: str) -> dict:
        """Creates teams from user-edited squad data, with optional overs limit, and returns the initial match state."""
        data = json.loads(squads_json) if isinstance(squads_json, str) else squads_json
        team1_data = data["teams"][0]
        team2_data = data["teams"][1]

        team1 = Team(team1_data["team_name"], [Player.from_dict(p) for p in team1_data["players"]])
        team2 = Team(team2_data["team_name"], [Player.from_dict(p) for p in team2_data["players"]])

        self.aus_team = team1
        self.eng_team = team2

        overs_limit = data.get("match_overs", 5)
        self.init_match(overs_limit=overs_limit)
        return self.get_state()

    def init_match(self, overs_limit=5):
        self.match = MatchState(self.aus_team, self.eng_team, overs_limit=overs_limit)
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
            "is_captain": player.is_captain,
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
            "over_summaries": innings.over_summaries,
            "innings_summary": innings.innings_summary,
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
                    "dismissal_mode": b.dismissal_mode,
                    "is_summary": getattr(b, "is_summary", False),
                    "summary_type": getattr(b, "summary_type", None)
                } for b in innings.commentary  # Send all deliveries including summaries
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
            "overs_limit": self.match.overs_limit,
            "match_result": self.match.match_result,
            "player_of_match": self.match.player_of_match.name if self.match.player_of_match else None,
            "team1_captain": self._get_captain_name(self.match.team1),
            "team2_captain": self._get_captain_name(self.match.team2),
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

        # 2.5. Generate LLM summaries (over / innings) if any were just created.
        #      A single ball can trigger both an over summary AND an innings summary
        #      (e.g., target chased on the last ball of an over), so check the last 2 entries.
        innings = self.match.current_innings
        for entry in reversed(innings.commentary[-2:]):
            if getattr(entry, "is_summary", False) and getattr(entry, "_llm_generated", False) is False:
                st = entry.summary_type
                if st == "over":
                    data = self._build_over_summary_data(innings)
                    llm_text = generate_summary("over", data)
                elif st == "innings":
                    data = self._build_innings_summary_data(innings)
                    llm_text = generate_summary("innings", data)
                else:
                    llm_text = None

                if llm_text:
                    entry.description = llm_text
                entry._llm_generated = True

        # 2.6. Generate match summary if the match just ended (innings 2 completed)
        if (self.match.innings_number == 2
                and self.match.innings2
                and self.match.innings2.is_completed
                and self.match.match_result
                and not getattr(self.match, '_match_summary_generated', False)):
            match_data = self._build_match_summary_data()
            llm_text = generate_summary("match", match_data)
            if llm_text:
                match_outcome = BallOutcome(
                    runs=0, batsman_name="", bowler_name="",
                    description=llm_text,
                )
                match_outcome.is_summary = True
                match_outcome.summary_type = "match"
                match_outcome._llm_generated = True
                self.match.innings2.commentary.append(match_outcome)

            # Add interview entries
            self._add_interview_entries()

            self.match._match_summary_generated = True

        # 3. Generate LLM commentary with ACCURATE post-delivery context
        innings = self.match.current_innings

        # --- Find the batsman who faced this ball ---
        batsman_player = None
        for p in innings.batting_team.players:
            if p.name == outcome.batsman_name:
                batsman_player = p
                break
        # Save PRE-delivery runs for milestone detection (step_ball already updated them)
        pre_delivery_runs = batsman_player.runs_scored - outcome.runs if batsman_player else 0
        # For wides/no-balls the batsman doesn't get credit, so runs stays the same
        if outcome.extra_type in ("w", "nb"):
            pre_delivery_runs = batsman_player.runs_scored if batsman_player else 0

        batsman_runs = batsman_player.runs_scored if batsman_player else 0
        batsman_balls = batsman_player.balls_faced if batsman_player else 0

        # --- Milestone detection ---
        milestone_text = None
        if batsman_player and not outcome.is_wicket and outcome.extra_type not in ("w", "nb"):
            milestones = [50, 100, 150, 200, 250]
            for m in milestones:
                if pre_delivery_runs < m and batsman_runs >= m:
                    milestone_text = f"{outcome.batsman_name} just passed {m} runs"
                    break

        # --- Collect the last 3 deliveries' commentary for context ---
        prev = innings.commentary[:-1]  # all except current
        recent_descriptions = [b.description for b in prev[-3:]]

        context = {
            "score": innings.score,
            "wickets": innings.wickets,
            "over_str": innings.overs_str,
            "bat_rating": outcome.bat_rating,
            "bowl_rating": outcome.bowl_rating,
            "batsman_runs": batsman_runs,
            "batsman_balls": batsman_balls,
            "recent_commentary": recent_descriptions,
        }
        if milestone_text:
            context["milestone"] = milestone_text

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
            context,
        )
        if llm_text:
            outcome.description = llm_text
            # Also update the dismissed batsman's dismissal_description so the
            # batting card's "How Out" column shows the LLM text, not the template.
            if outcome.is_wicket and outcome.dismissed_batsman_name:
                for p in innings.batting_team.players:
                    if p.name == outcome.dismissed_batsman_name:
                        p.dismissal_description = llm_text
                        break

        return self.get_state()

    # ------------------------------------------------------------------
    # Summary data builders (for LLM prompts)
    # ------------------------------------------------------------------

    def _get_over_ball_breakdown(self, innings) -> str:
        """Build a ball-by-ball summary of the last 6 legal deliveries."""
        balls = []
        count = 0
        for outcome in reversed(innings.commentary):
            if getattr(outcome, "is_summary", False):
                continue
            if outcome.extra_type not in ("w", "nb"):
                count += 1
                if outcome.is_wicket:
                    desc = f"WICKET ({outcome.wicket_type}) — {outcome.dismissed_batsman_name} out"
                elif outcome.extra_type:
                    et = {"w": "Wide", "nb": "No-ball", "b": "Byes", "lb": "Leg-byes"}.get(outcome.extra_type, outcome.extra_type)
                    desc = f"{et} — {outcome.extras} extra"
                else:
                    desc = f"{outcome.runs} run(s)"
                balls.append(f"{outcome.batsman_name}: {desc}")
                if count == 6:
                    break
        return "; ".join(reversed(balls)) if balls else ""

    def _compute_partnerships(self, fow: list, total_score: int) -> list:
        """Compute partnerships from FOW. Returns top 3 by runs."""
        partnerships = []
        prev_score = 0
        for entry in fow:
            runs = entry["score"] - prev_score
            partnerships.append({
                "wicket": entry["wicket"],
                "runs": runs,
                "dismissed": entry["player"],
            })
            prev_score = entry["score"]
        # The final unbroken partnership
        if total_score > prev_score:
            partnerships.append({
                "wicket": "unbroken",
                "runs": total_score - prev_score,
                "dismissed": "not out",
            })
        partnerships.sort(key=lambda p: -p["runs"])
        return partnerships[:3]

    def _find_collapses(self, fow: list) -> list:
        """Find wicket collapses — periods where wickets fell quickly for few runs."""
        if len(fow) < 3:
            return []
        collapses = []
        for start in range(len(fow)):
            for end in range(start + 1, len(fow)):
                wkts = end - start + 1
                runs_lost = fow[end]["score"] - fow[start]["score"]
                # A collapse: 3+ wickets for < 10 runs/wicket, or 2 wickets for ≤ 15 total
                if (wkts >= 3 and runs_lost < wkts * 10) or (wkts >= 2 and runs_lost <= 15):
                    collapses.append({
                        "wickets": wkts,
                        "runs": runs_lost,
                        "from_score": fow[start]["score"],
                        "to_score": fow[end]["score"],
                        "from_wicket": fow[start]["wicket"],
                        "to_wicket": fow[end]["wicket"],
                        "severity": wkts / max(runs_lost, 1),
                    })
        collapses.sort(key=lambda c: -c["severity"])
        return collapses[:2]

    def _get_bowler_table(self, innings) -> list:
        """Return all bowlers with wickets, economy, overs for the innings."""
        bowlers = []
        for p in innings.bowling_team.players:
            if p.balls_bowled > 0:
                bowlers.append({
                    "name": p.name,
                    "wkts": p.wickets_taken,
                    "runs": p.runs_conceded,
                    "overs": p.overs_bowled,
                    "econ": round(p.economy_rate, 2),
                })
        return bowlers

    def _build_over_summary_data(self, innings) -> dict:
        """Collect detailed data for an end-of-over summary."""
        if not innings.over_summaries:
            return {}
        ov = innings.over_summaries[-1]
        overs_float = innings.balls_bowled / 6.0
        run_rate = innings.score / overs_float if overs_float > 0 else 0.0
        ball_breakdown = self._get_over_ball_breakdown(innings)
        return {
            "summary_type": "over",
            "over_number": ov["over_number"],
            "runs": ov["runs"],
            "wickets": ov["wickets"],
            "bowler_name": ov["bowler_name"],
            "is_maiden": ov["is_maiden"],
            "score": ov["score"],
            "total_wickets": ov["total_wickets"],
            "over_str": ov["over_str"],
            "run_rate": round(run_rate, 2),
            "ball_breakdown": ball_breakdown,
            "striker_name": innings.striker.name if innings.striker else "",
            "non_striker_name": innings.non_striker.name if innings.non_striker else "",
        }

    def _build_innings_summary_data(self, innings) -> dict:
        """Collect detailed data for an end-of-innings summary."""
        # Top scorer
        top_scorer = None
        top_runs = 0
        for p in innings.batting_team.players:
            if p.runs_scored > top_runs:
                top_runs = p.runs_scored
                top_scorer = p

        # Best bowler
        best_bowler = None
        best_wkts = 0
        best_econ = 99.0
        for p in innings.bowling_team.players:
            if p.wickets_taken > best_wkts or (p.wickets_taken == best_wkts and p.economy_rate < best_econ):
                best_wkts = p.wickets_taken
                best_econ = p.economy_rate
                best_bowler = p

        overs_float = innings.balls_bowled / 6.0
        run_rate = innings.score / overs_float if overs_float > 0 else 0.0

        # Partnerships
        partnerships = self._compute_partnerships(innings.fall_of_wickets, innings.score)

        # Collapses
        collapses = self._find_collapses(innings.fall_of_wickets)

        # Bowler table
        bowlers = self._get_bowler_table(innings)
        # Top 3 wicket-takers
        top_bowlers = sorted(bowlers, key=lambda b: (-b["wkts"], b["econ"]))[:3]
        # Economy extremes
        econ_high = max(bowlers, key=lambda b: b["econ"]) if bowlers else None
        econ_low = min(bowlers, key=lambda b: b["econ"]) if bowlers else None

        data = {
            "summary_type": "innings",
            "batting_team": innings.batting_team.name,
            "score": innings.score,
            "wickets": innings.wickets,
            "overs": innings.overs_str,
            "run_rate": round(run_rate, 2),
            "extras": innings.total_extras,
            "extras_breakdown": f"w:{innings.extras['wides']} nb:{innings.extras['noballs']} b:{innings.extras['byes']} lb:{innings.extras['legbyes']}",
            "partnerships": [
                f"Wkt {p['wicket']}: {p['runs']} runs ({p['dismissed']})"
                for p in partnerships
            ],
            "collapses": [
                f"Wickets {c['from_wicket']}-{c['to_wicket']}: {c['wickets']}wkts/{c['runs']}runs (score went {c['from_score']}-{c['to_score']})"
                for c in collapses
            ],
            "top_bowlers": [
                f"{b['name']} {b['wkts']}/{b['runs']} ({b['overs']} Ov, Econ {b['econ']})"
                for b in top_bowlers
            ],
            "econ_worst": f"{econ_high['name']} {econ_high['econ']}" if econ_high else None,
            "econ_best": f"{econ_low['name']} {econ_low['econ']}" if econ_low else None,
        }
        if top_scorer:
            data["top_scorer"] = {
                "name": top_scorer.name,
                "runs": top_scorer.runs_scored,
                "balls": top_scorer.balls_faced,
                "sr": round(top_scorer.strike_rate, 1),
            }
        if best_bowler and best_bowler.wickets_taken > 0:
            data["best_bowler"] = {
                "name": best_bowler.name,
                "wkts": best_bowler.wickets_taken,
                "runs": best_bowler.runs_conceded,
                "overs": best_bowler.overs_bowled,
                "econ": round(best_bowler.economy_rate, 2),
            }
        return data

    def _build_match_summary_data(self) -> dict:
        """Collect detailed data for the end-of-match summary."""
        m = self.match
        inns1 = m.innings1
        inns2 = m.innings2
        potm = m.player_of_match

        # Innings summaries for both sides
        inns1_data = self._build_innings_summary_data(inns1)
        inns2_data = self._build_innings_summary_data(inns2)

        return {
            "summary_type": "match",
            "result": m.match_result["text"] if m.match_result else "Match concluded",
            "team1_name": m.team1.name,
            "team1_score": f"{inns1.score}/{inns1.wickets}",
            "team1_overs": inns1.overs_str,
            "team2_name": m.team2.name,
            "team2_score": f"{inns2.score}/{inns2.wickets}",
            "team2_overs": inns2.overs_str,
            "potm_name": potm.name if potm else None,
            "potm_runs": potm.runs_scored if potm else 0,
            "potm_wickets": potm.wickets_taken if potm else 0,
            "innings1": inns1_data,
            "innings2": inns2_data,
        }

    def _get_captain_name(self, team) -> str:
        """Return the captain's name for a team, or the first player if none designated."""
        for p in team.players:
            if p.is_captain:
                return p.name
        return team.players[0].name if team.players else "Unknown"

    def _add_interview_entries(self):
        """Add post-match interview commentary entries (captains + POTM) to the commentary feed."""
        m = self.match
        if not m.match_result:
            return

        winner_name = m.match_result.get("winner_name")
        potm_name = m.match_result.get("potm_name")
        potm_team = m.match_result.get("potm_team", "")

        # Captain names
        team1_captain = self._get_captain_name(m.team1)
        team2_captain = self._get_captain_name(m.team2)
        winning_captain = None
        losing_captain = None
        if winner_name:
            if winner_name == m.team1.name:
                winning_captain = team1_captain
                losing_captain = team2_captain
            else:
                winning_captain = team2_captain
                losing_captain = team1_captain

        innings = self.match.innings2

        # Winning captain interview
        if winning_captain:
            entry = BallOutcome(
                runs=0, batsman_name="", bowler_name="",
                description=f"🏆 {winning_captain} (winning captain): \"I'm absolutely thrilled with the team's performance today. The boys showed great character out there.\"",
            )
            entry.is_summary = True
            entry.summary_type = "interview"
            innings.commentary.append(entry)

        # Losing captain interview
        if losing_captain:
            entry = BallOutcome(
                runs=0, batsman_name="", bowler_name="",
                description=f"📢 {losing_captain} (losing captain): \"Credit to the opposition, they outplayed us today. We'll learn from this and come back stronger.\"",
            )
            entry.is_summary = True
            entry.summary_type = "interview"
            innings.commentary.append(entry)

        # POTM interview
        if potm_name:
            entry = BallOutcome(
                runs=0, batsman_name="", bowler_name="",
                description=f"⭐ {potm_name} ({potm_team}): \"I'm really happy to contribute to the team's win. The boys made it easy for me out there.\"",
            )
            entry.is_summary = True
            entry.summary_type = "interview"
            innings.commentary.append(entry)

    def _milestone_prefix(self, milestone: int) -> str:
        """Return the article/noun for a milestone number."""
        return milestone  # Pass through raw number

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
