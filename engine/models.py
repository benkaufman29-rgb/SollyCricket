import json

class Player:
    def __init__(self, name, role, batting_hand, bowling_type, batting_order, ratings):
        self.name = name
        self.role = role
        self.batting_hand = batting_hand
        self.bowling_type = bowling_type
        self.batting_order = batting_order
        self.ratings = ratings
        
        # Innings batting stats
        self.runs_scored = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.dismissal = ""  # e.g., "c Smith b Starc" or "not out"
        self.dismissal_description = ""  # Full commentary description of the dismissal
        self.status = "dnb"  # "dnb" (did not bat), "batting", "out", "not out"
        
        # Innings bowling stats
        self.balls_bowled = 0
        self.runs_conceded = 0
        self.wickets_taken = 0
        self.maidens = 0
        self.current_over_runs = 0  # To track maidens
        self.current_over_balls = 0

    @property
    def strike_rate(self):
        if self.balls_faced == 0:
            return 0.0
        return (self.runs_scored / self.balls_faced) * 100.0

    @property
    def economy_rate(self):
        overs = self.balls_bowled / 6.0
        if overs == 0:
            return 0.0
        return self.runs_conceded / overs

    @property
    def overs_bowled(self):
        overs = self.balls_bowled // 6
        balls = self.balls_bowled % 6
        return f"{overs}.{balls}"

    def reset_stats(self):
        self.runs_scored = 0
        self.balls_faced = 0
        self.fours = 0
        self.sixes = 0
        self.dismissal = ""
        self.dismissal_description = ""
        self.status = "dnb"
        self.balls_bowled = 0
        self.runs_conceded = 0
        self.wickets_taken = 0
        self.maidens = 0
        self.current_over_runs = 0
        self.current_over_balls = 0

    def to_dict(self):
        return {
            "name": self.name,
            "role": self.role,
            "batting_hand": self.batting_hand,
            "bowling_type": self.bowling_type,
            "batting_order": self.batting_order,
            "ratings": self.ratings
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            role=data["role"],
            batting_hand=data["batting_hand"],
            bowling_type=data["bowling_type"],
            batting_order=data["batting_order"],
            ratings=data["ratings"]
        )


class Team:
    def __init__(self, name, players):
        self.name = name
        # Sort players by batting order
        self.players = sorted(players, key=lambda p: p.batting_order)

    def reset_stats(self):
        for player in self.players:
            player.reset_stats()

    @classmethod
    def from_json_file(cls, filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
        players = [Player.from_dict(p) for p in data["players"]]
        return cls(name=data["team_name"], players=players)


class BallOutcome:
    def __init__(self, runs=0, extras=0, extra_type=None, is_wicket=False, wicket_type=None,
                 batsman_name="", bowler_name="", dismissed_batsman_name=None, description="",
                 dismissal_mode="", fielder_name=None, bat_rating=0.5, bowl_rating=0.5):
        self.runs = runs  # Runs scored off bat
        self.extras = extras  # Extra runs (wides, no balls, byes, legbyes)
        self.extra_type = extra_type  # "w" (wide), "nb" (no-ball), "b" (bye), "lb" (leg-bye)
        self.is_wicket = is_wicket
        self.wicket_type = wicket_type  # "bowled", "caught", "lbw", "runout", "stumped", etc.
        self.batsman_name = batsman_name
        self.bowler_name = bowler_name
        self.dismissed_batsman_name = dismissed_batsman_name
        self.fielder_name = fielder_name  # Fielder involved in wicket/dismissal
        self.description = description  # Commentary text
        self.dismissal_mode = dismissal_mode  # e.g., "c Smith b Starc"
        self.bat_rating = bat_rating  # Batsman's batting rating at time of delivery
        self.bowl_rating = bowl_rating  # Bowler's bowling rating at time of delivery

    @property
    def total_runs(self):
        return self.runs + self.extras

    def __str__(self):
        out_str = f"{self.batsman_name} to {self.bowler_name}: "
        if self.is_wicket:
            out_str += f"WICKET ({self.wicket_type})"
        else:
            out_str += f"{self.total_runs} run(s)"
            if self.extra_type:
                out_str += f" ({self.extra_type})"
        return out_str


class Innings:
    def __init__(self, batting_team, bowling_team, overs_limit=None, target=None):
        self.batting_team = batting_team
        self.bowling_team = bowling_team
        self.overs_limit = overs_limit
        self.target = target  # Run chase target (if 2nd innings)
        
        self.score = 0
        self.wickets = 0
        self.balls_bowled = 0
        self.extras = {"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0}
        self.commentary = []  # List of BallOutcome objects
        self.fall_of_wickets = []  # List of dicts: {"wicket": 1, "score": 25, "overs": "4.2", "player": "Name"}
        self.is_completed = False
        
        # State tracking for active players
        self.striker = None
        self.non_striker = None
        self.current_bowler = None
        
        # For tracking active partners and order of next batsmen
        self._next_batting_index = 0
        self._bowling_rotation = []  # Log bowler switches if needed

    @property
    def total_extras(self):
        return sum(self.extras.values())

    @property
    def overs_str(self):
        overs = self.balls_bowled // 6
        balls = self.balls_bowled % 6
        return f"{overs}.{balls}"

    def initialize_innings(self):
        self.batting_team.reset_stats()
        self.bowling_team.reset_stats()
        
        self.score = 0
        self.wickets = 0
        self.balls_bowled = 0
        self.extras = {"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0}
        self.commentary = []
        self.fall_of_wickets = []
        self.is_completed = False
        
        # Set up openers
        self.striker = self.batting_team.players[0]
        self.non_striker = self.batting_team.players[1]
        self.striker.status = "batting"
        self.non_striker.status = "batting"
        self._next_batting_index = 2
        
        # Set default bowler (usually the last bowler or premier bowler)
        self.current_bowler = self.bowling_team.players[-1] # Default to bowler 11

    def change_bowler(self, bowler):
        if self.current_bowler and self.current_bowler.current_over_balls > 0:
            # Bowler cannot change mid-over unless injured
            pass
        self.current_bowler = bowler

    def record_delivery(self, outcome):
        # Update commentary
        self.commentary.append(outcome)
        
        # 1. Update ball stats
        is_legal_delivery = outcome.extra_type not in ["w", "nb"]
        
        if is_legal_delivery:
            self.balls_bowled += 1
            if self.striker:
                self.striker.balls_faced += 1
            if self.current_bowler:
                self.current_bowler.balls_bowled += 1
                self.current_bowler.current_over_balls += 1

        # 2. Update runs
        self.score += outcome.total_runs
        
        # Update batsman runs
        if self.striker and outcome.runs > 0:
            self.striker.runs_scored += outcome.runs
            if outcome.runs == 4:
                self.striker.fours += 1
            elif outcome.runs == 6:
                self.striker.sixes += 1

        # Update extras
        if outcome.extra_type:
            ext_key = {
                "w": "wides",
                "nb": "noballs",
                "b": "byes",
                "lb": "legbyes"
            }.get(outcome.extra_type)
            if ext_key:
                self.extras[ext_key] += outcome.extras
        
        # Update bowler runs conceded
        if self.current_bowler:
            # Wides and no-balls are credited to bowler's runs conceded.
            # Byes and leg-byes are not credited to bowler.
            runs_to_bowler = outcome.runs
            if outcome.extra_type in ["w", "nb"]:
                runs_to_bowler += outcome.extras
            self.current_bowler.runs_conceded += runs_to_bowler
            self.current_bowler.current_over_runs += runs_to_bowler

        # 3. Update wickets
        if outcome.is_wicket:
            self.wickets += 1
            
            # Dismiss batsman
            dismissed_bat = self.striker
            if outcome.dismissed_batsman_name == self.non_striker.name:
                dismissed_bat = self.non_striker
            
            dismissed_bat.status = "out"
            dismissed_bat.dismissal = outcome.dismissal_mode or f"out ({outcome.wicket_type})"
            dismissed_bat.dismissal_description = outcome.description
            
            # Update bowler wickets if it's a bowler's wicket (not runout)
            if self.current_bowler and outcome.wicket_type != "runout":
                self.current_bowler.wickets_taken += 1
                
            # Log Fall of Wicket
            self.fall_of_wickets.append({
                "wicket": self.wickets,
                "score": self.score,
                "overs": self.overs_str,
                "player": dismissed_bat.name
            })
            
            # Bring in next batsman if available
            if self.wickets < 10 and self._next_batting_index < len(self.batting_team.players):
                new_bat = self.batting_team.players[self._next_batting_index]
                new_bat.status = "batting"
                self._next_batting_index += 1
                if dismissed_bat == self.striker:
                    self.striker = new_bat
                else:
                    self.non_striker = new_bat
            else:
                # All out or no more batsmen
                self.is_completed = True
                if self.striker and self.striker.status == "batting":
                    self.striker.status = "not out"
                if self.non_striker and self.non_striker.status == "batting":
                    self.non_striker.status = "not out"
                self.striker = None
                self.non_striker = None

        # 4. Check over completion
        if is_legal_delivery and self.balls_bowled % 6 == 0 and not self.is_completed:
            # Over complete!
            # Check maiden
            if self.current_bowler:
                if self.current_bowler.current_over_runs == 0:
                    self.current_bowler.maidens += 1
                self.current_bowler.current_over_runs = 0
                self.current_bowler.current_over_balls = 0
            
            # Rotate strike at the end of the over
            if self.striker and self.non_striker:
                self.striker, self.non_striker = self.non_striker, self.striker
        
        # Rotate strike on odd runs (if not end of over or wicket)
        elif not outcome.is_wicket and is_legal_delivery:
            runs_for_strike_rotation = outcome.runs
            if outcome.extra_type in ["b", "lb"]:
                runs_for_strike_rotation = outcome.extras
            
            if runs_for_strike_rotation in [1, 3, 5]:
                if self.striker and self.non_striker:
                    self.striker, self.non_striker = self.non_striker, self.striker

        # 5. Check match termination criteria
        # Target chased?
        if self.target is not None and self.score >= self.target:
            self.is_completed = True
            if self.striker:
                self.striker.status = "not out"
            if self.non_striker:
                self.non_striker.status = "not out"
            self.striker = None
            self.non_striker = None
            
        # Overs limit reached?
        if self.overs_limit is not None and (self.balls_bowled >= self.overs_limit * 6):
            self.is_completed = True
            if self.striker:
                self.striker.status = "not out"
            if self.non_striker:
                self.non_striker.status = "not out"
            self.striker = None
            self.non_striker = None


class MatchState:
    def __init__(self, team1, team2, overs_limit=None):
        self.team1 = team1
        self.team2 = team2
        self.overs_limit = overs_limit
        
        self.innings1 = Innings(team1, team2, overs_limit=overs_limit)
        self.innings2 = None  # Initialized when 2nd innings starts
        self.current_innings = self.innings1
        self.innings_number = 1
        self.status_message = "Match yet to start."
        
    def start_match(self):
        self.innings1.initialize_innings()
        self.current_innings = self.innings1
        self.innings_number = 1
        self.status_message = f"Innings 1: {self.team1.name} batting"

    def start_second_innings(self):
        target = self.innings1.score + 1
        self.innings2 = Innings(self.team2, self.team1, overs_limit=self.overs_limit, target=target)
        self.innings2.initialize_innings()
        self.current_innings = self.innings2
        self.innings_number = 2
        self.status_message = f"Innings 2: {self.team2.name} chasing {target}"

    def step_ball(self, outcome):
        if self.current_innings.is_completed:
            return
        
        self.current_innings.record_delivery(outcome)
        
        # Check if current innings ended
        if self.current_innings.is_completed:
            if self.innings_number == 1:
                self.status_message = f"Innings 1 complete. {self.team1.name} scored {self.innings1.score}/{self.innings1.wickets}."
            else:
                # 2nd innings completed. Who won?
                if self.innings2.score >= self.innings2.target:
                    wickets_left = 10 - self.innings2.wickets
                    self.status_message = f"{self.team2.name} won by {wickets_left} wickets!"
                elif self.innings2.score < self.innings2.target - 1:
                    runs_short = (self.innings2.target - 1) - self.innings2.score
                    self.status_message = f"{self.team1.name} won by {runs_short} runs!"
                else:
                    self.status_message = "Match tied!"
