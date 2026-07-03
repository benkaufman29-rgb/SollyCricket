import random
from engine.models import BallOutcome, Team, Player
from engine.commentary_templates import COMMENTARY_TEMPLATES


def get_next_bowler(batting_team: Team, bowling_team: Team, current_bowler: Player) -> Player:
    """Picks a reasonable bowler to bowl the next over."""
    # Find all players classified as Bowlers or All-rounders, excluding the current bowler
    bowlers = [p for p in bowling_team.players if p.role in ["Bowler", "All-rounder"] and p != current_bowler]

    # Fallback to any player if needed
    if not bowlers:
        bowlers = [p for p in bowling_team.players if p != current_bowler]

    # Pick randomly from the available bowlers
    return random.choice(bowlers)



def simulate_delivery(batting_team, bowling_team, striker, non_striker, bowler):
    """
    Simulates a delivery based on striker and bowler ratings.
    Returns a BallOutcome object with template-based commentary.
    """
    # 1. Determine Wicket Probability
    # Base probability of a wicket in a typical delivery is around 4% (0.04)
    # Bowler's bowling rating vs striker's batting rating alters this.
    bat_rating = striker.ratings.get("batting", 0.5)
    bowl_rating = bowler.ratings.get("bowling", 0.5)

    prob_wicket = 0.04 + (bowl_rating - bat_rating) * 0.02
    prob_wicket = max(0.01, min(0.12, prob_wicket))

    # 2. Determine Extras Probability
    # Wides ~ 2%, No-balls ~ 0.5%, Byes/Leg-byes ~ 0.5%
    prob_wide = 0.02
    prob_noball = 0.005
    prob_bye_legbye = 0.005

    r = random.random()

    # Wicket event
    if r < prob_wicket:
        wicket_types = ["caught", "bowled", "lbw", "runout", "stumped"]
        # Weights: caught 60%, bowled 15%, lbw 15%, runout 5%, stumped 5%
        wicket_type = random.choices(wicket_types, weights=[0.60, 0.15, 0.15, 0.05, 0.05], k=1)[0]

        dismissed_batsman_name = striker.name
        fielder_name = None

        # Select a fielder (any player on the bowling team other than the bowler)
        fielders = [p for p in bowling_team.players if p.name != bowler.name]
        if fielders:
            fielder_name = random.choice(fielders).name

        # For runouts, it could be either batsman dismissed
        if wicket_type == "runout":
            dismissed_batsman_name = random.choice([striker.name, non_striker.name])

        # Get template description
        template_key = f"wicket_{wicket_type}"
        template = random.choice(COMMENTARY_TEMPLATES[template_key])
        description = template.format(
            batsman=dismissed_batsman_name,
            bowler=bowler.name,
            fielder=fielder_name or "a fielder"
        )

        # Generate dismissal mode string (e.g., "c Smith b Starc")
        dismissal_mode = ""
        if wicket_type == "caught":
            dismissal_mode = f"c {fielder_name or '?'} b {bowler.name}"
        elif wicket_type == "bowled":
            dismissal_mode = f"b {bowler.name}"
        elif wicket_type == "lbw":
            dismissal_mode = f"lbw b {bowler.name}"
        elif wicket_type == "runout":
            dismissal_mode = f"run out ({fielder_name or '?'})"
        elif wicket_type == "stumped":
            dismissal_mode = f"st {fielder_name or '?'} b {bowler.name}"

        outcome = BallOutcome(
            runs=0,
            extras=0,
            extra_type=None,
            is_wicket=True,
            wicket_type=wicket_type,
            batsman_name=striker.name,
            bowler_name=bowler.name,
            dismissed_batsman_name=dismissed_batsman_name,
            fielder_name=fielder_name,
            description=description,
            dismissal_mode=dismissal_mode,
            bat_rating=bat_rating,
            bowl_rating=bowl_rating,
        )

    # Extras events
    elif r < prob_wicket + prob_wide:
        # Wide (gives 1 extra, no ball bowled)
        description = random.choice(COMMENTARY_TEMPLATES["wide"]).format(bowler=bowler.name)
        outcome = BallOutcome(
            runs=0,
            extras=1,
            extra_type="w",
            is_wicket=False,
            batsman_name=striker.name,
            bowler_name=bowler.name,
            description=description,
            bat_rating=bat_rating,
            bowl_rating=bowl_rating,
        )

    elif r < prob_wicket + prob_wide + prob_noball:
        # No-ball (gives 1 extra + batsman can score off bat. For simplicity, batsman gets 0 runs off bat here)
        description = random.choice(COMMENTARY_TEMPLATES["noball"]).format(bowler=bowler.name)
        outcome = BallOutcome(
            runs=0,
            extras=1,
            extra_type="nb",
            is_wicket=False,
            batsman_name=striker.name,
            bowler_name=bowler.name,
            description=description,
            bat_rating=bat_rating,
            bowl_rating=bowl_rating,
        )

    elif r < prob_wicket + prob_wide + prob_noball + prob_bye_legbye:
        # Bye/Leg-bye (runs added to team total as extras, legal delivery, not credited to batsman/bowler)
        runs_scored = random.choices([1, 2, 4], weights=[0.80, 0.15, 0.05], k=1)[0]
        extra_type = random.choice(["b", "lb"])
        template_key = "bye" if extra_type == "b" else "legbye"
        description = random.choice(COMMENTARY_TEMPLATES[template_key])

        outcome = BallOutcome(
            runs=0,
            extras=runs_scored,
            extra_type=extra_type,
            is_wicket=False,
            batsman_name=striker.name,
            bowler_name=bowler.name,
            description=description,
            bat_rating=bat_rating,
            bowl_rating=bowl_rating,
        )

    # Runs off the bat events
    else:
        # Determine runs based on batsman ratings
        # High rating batsman has higher probability of 4s and 6s, and lower dot ball chance.
        p_dot = max(0.25, 0.55 - 0.25 * bat_rating)
        p_one = 0.30
        p_two = 0.06
        p_three = 0.01
        p_four = 0.05 + 0.15 * bat_rating
        p_six = 0.005 + 0.075 * bat_rating

        runs_options = [0, 1, 2, 3, 4, 6]
        weights = [p_dot, p_one, p_two, p_three, p_four, p_six]

        runs = random.choices(runs_options, weights=weights, k=1)[0]

        runs_map = {
            0: "dot",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            6: "six"
        }

        template_key = runs_map[runs]
        template = random.choice(COMMENTARY_TEMPLATES[template_key])
        description = template.format(batsman=striker.name, bowler=bowler.name)

        outcome = BallOutcome(
            runs=runs,
            extras=0,
            extra_type=None,
            is_wicket=False,
            batsman_name=striker.name,
            bowler_name=bowler.name,
            description=description,
            bat_rating=bat_rating,
            bowl_rating=bowl_rating,
        )

    return outcome
