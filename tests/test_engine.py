import unittest
from engine.models import Player, Team, Innings, MatchState, BallOutcome

class TestEngine(unittest.TestCase):
    def setUp(self):
        # Create test teams
        self.batting_players = [
            Player("Batsman 1", "Batsman", "Right-hand bat", "None", 1, {"batting": 0.8, "bowling": 0.0}),
            Player("Batsman 2", "Batsman", "Right-hand bat", "None", 2, {"batting": 0.8, "bowling": 0.0}),
            Player("Batsman 3", "Batsman", "Right-hand bat", "None", 3, {"batting": 0.7, "bowling": 0.0}),
            Player("Batsman 4", "Batsman", "Right-hand bat", "None", 4, {"batting": 0.6, "bowling": 0.0}),
            Player("Batsman 5", "Batsman", "Right-hand bat", "None", 5, {"batting": 0.5, "bowling": 0.0}),
            Player("Batsman 6", "Batsman", "Right-hand bat", "None", 6, {"batting": 0.4, "bowling": 0.0}),
            Player("Batsman 7", "Wicketkeeper-Batsman", "Right-hand bat", "None", 7, {"batting": 0.3, "bowling": 0.0}),
            Player("Bowler 8", "Bowler", "Right-hand bat", "Right-arm fast", 8, {"batting": 0.2, "bowling": 0.7}),
            Player("Bowler 9", "Bowler", "Right-hand bat", "Right-arm fast", 9, {"batting": 0.1, "bowling": 0.8}),
            Player("Bowler 10", "Bowler", "Right-hand bat", "Right-arm fast", 10, {"batting": 0.0, "bowling": 0.8}),
            Player("Bowler 11", "Bowler", "Right-hand bat", "Right-arm fast", 11, {"batting": 0.0, "bowling": 0.9}),
        ]
        self.bowling_players = [
            Player("Opp Bowler 1", "Bowler", "Right-hand bat", "Right-arm offbreak", 1, {"batting": 0.1, "bowling": 0.75}),
            # (Just copy players for simplicity)
        ] + [
            Player(f"Opp Player {i}", "Batsman", "Right-hand bat", "None", i, {"batting": 0.5, "bowling": 0.0})
            for i in range(2, 12)
        ]
        
        self.bat_team = Team("Batters", self.batting_players)
        self.bowl_team = Team("Bowlers", self.bowling_players)
        
    def test_innings_initialization(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        self.assertEqual(innings.score, 0)
        self.assertEqual(innings.wickets, 0)
        self.assertEqual(innings.balls_bowled, 0)
        self.assertEqual(innings.striker.name, "Batsman 1")
        self.assertEqual(innings.non_striker.name, "Batsman 2")
        self.assertEqual(innings.striker.status, "batting")
        self.assertEqual(innings.non_striker.status, "batting")
        self.assertEqual(self.bat_team.players[2].status, "dnb")

    def test_record_dot_ball(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        outcome = BallOutcome(runs=0, batsman_name="Batsman 1", bowler_name="Opp Bowler 1")
        innings.record_delivery(outcome)
        
        self.assertEqual(innings.score, 0)
        self.assertEqual(innings.balls_bowled, 1)
        self.assertEqual(innings.striker.runs_scored, 0)
        self.assertEqual(innings.striker.balls_faced, 1)
        self.assertEqual(innings.current_bowler.balls_bowled, 1)
        self.assertEqual(innings.current_bowler.runs_conceded, 0)

    def test_strike_rotation_on_single(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        initial_striker = innings.striker
        initial_non_striker = innings.non_striker
        
        outcome = BallOutcome(runs=1, batsman_name=initial_striker.name, bowler_name="Opp Bowler 1")
        innings.record_delivery(outcome)
        
        self.assertEqual(innings.score, 1)
        self.assertEqual(innings.striker.name, initial_non_striker.name)
        self.assertEqual(innings.non_striker.name, initial_striker.name)
        self.assertEqual(initial_striker.runs_scored, 1)
        self.assertEqual(initial_striker.balls_faced, 1)

    def test_over_completion_strike_rotation(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        initial_striker = innings.striker
        initial_non_striker = innings.non_striker
        
        # Bowl 5 dot balls (no strike rotation)
        for _ in range(5):
            outcome = BallOutcome(runs=0, batsman_name=innings.striker.name, bowler_name=innings.current_bowler.name)
            innings.record_delivery(outcome)
            
        # At this point, initial_striker has faced 5 balls and is still striking.
        self.assertEqual(innings.striker.name, initial_striker.name)
        
        # Bowl 6th ball (runs=0) to complete the over
        outcome = BallOutcome(runs=0, batsman_name=innings.striker.name, bowler_name=innings.current_bowler.name)
        innings.record_delivery(outcome)
        
        # Over is complete (6 balls). Striker should rotate at the end of the over.
        self.assertEqual(innings.balls_bowled, 6)
        self.assertEqual(innings.striker.name, initial_non_striker.name)
        self.assertEqual(innings.non_striker.name, initial_striker.name)

    def test_wicket_fall(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        initial_striker = innings.striker
        
        outcome = BallOutcome(runs=0, is_wicket=True, wicket_type="caught",
                              batsman_name=initial_striker.name, bowler_name=innings.current_bowler.name,
                              dismissed_batsman_name=initial_striker.name, description="Caught out!",
                              dismissal_mode="c Smith b Jones")
        innings.record_delivery(outcome)

        self.assertEqual(innings.wickets, 1)
        self.assertEqual(initial_striker.status, "out")
        self.assertEqual(initial_striker.dismissal, "c Smith b Jones")
        self.assertEqual(initial_striker.dismissal_description, "Caught out!")
        
        # New batsman should be "Batsman 3" (batting_order 3)
        self.assertEqual(innings.striker.name, "Batsman 3")
        self.assertEqual(innings.striker.status, "batting")
        self.assertEqual(innings.non_striker.name, "Batsman 2")

    def test_all_out(self):
        innings = Innings(self.bat_team, self.bowl_team)
        innings.initialize_innings()
        
        # Take 10 wickets sequentially
        for i in range(10):
            striker_name = innings.striker.name
            outcome = BallOutcome(runs=0, is_wicket=True, wicket_type="bowled",
                                  batsman_name=striker_name, bowler_name=innings.current_bowler.name,
                                  dismissed_batsman_name=striker_name)
            innings.record_delivery(outcome)
            
        self.assertEqual(innings.wickets, 10)
        self.assertTrue(innings.is_completed)
        self.assertIsNone(innings.striker)
        self.assertIsNone(innings.non_striker)

if __name__ == '__main__':
    unittest.main()
