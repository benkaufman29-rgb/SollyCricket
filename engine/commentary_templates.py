"""Shared commentary template data — used by both simulator and commentary_llm."""

COMMENTARY_TEMPLATES = {
    "dot": [
        "{batsman} defends it back to the bowler.",
        "{batsman} leaves that one alone as it carries through to the keeper.",
        "{batsman} pushes it to mid-off, no run.",
        "Solid defensive stroke from {batsman}.",
        "Beaten! {bowler} finds some movement past the outside edge of {batsman}'s bat.",
        "{batsman} blocks it down into the pitch."
    ],
    "one": [
        "{batsman} tucks it off his hips for a single.",
        "{batsman} taps it to deep cover and gets off strike.",
        "Guided away to third man for a comfortable single.",
        "{batsman} drives it down to long-on for one.",
        "Flicked away through midwicket for a single.",
        "Short ball, pulled away to deep square leg for one run."
    ],
    "two": [
        "{batsman} clips it through the gaps in the outfield and they run hard for two.",
        "Driven through the covers, nice sliding stop prevents the boundary. Two runs.",
        "{batsman} flicks it off the pads to deep midwicket and comes back for the second.",
        "Lofted over the infield, lands in no man's land. They pick up two.",
        "Pushed into the gap at extra cover, excellent running gets them two."
    ],
    "three": [
        "Superb timing! Driven through extra cover. The outfield is slow, and they run three.",
        "Glanced fine down the leg side, the fielder chases it down. Excellent running for three.",
        "Cut away past point, great backup fielding saves a run. Three runs."
    ],
    "four": [
        "{batsman} drives gracefully through the covers for four! Beautiful stroke.",
        "{batsman} crunches that away through point for a boundary! What a shot.",
        "{batsman} straight drives it past the bowler, racing away to the boundary for four!",
        "Short ball, pulled away imperiously by {batsman} to the boundary for four!",
        "{batsman} leans into it and flicks it through midwicket for four runs!"
    ],
    "six": [
        "{batsman} dances down the track and lofts it high over long-on for SIX!",
        "Struck clean! {batsman} pulls it over deep square leg, into the stands for a massive SIX!",
        "{batsman} slog sweeps it over the midwicket boundary for a flat SIX!",
        "Stand and deliver! {batsman} dispatches {bowler} over the bowler's head for a colossal SIX!"
    ],
    "wide": [
        "Wayward delivery from {bowler}, spraying it down the leg side. Wide called.",
        "Too wide outside off stump, the umpire signals wide.",
        "Short and sailing over the batsman's head, wide called."
    ],
    "noball": [
        "{bowler} oversteps! No-ball called. Free hit coming up (simulated next ball).",
        "High full toss above waist height from {bowler}, called a no-ball."
    ],
    "bye": [
        "Beaten batsman, beaten keeper! The ball races away for byes.",
        "Through the gate, but misses the stumps and keeper. They sneak byes."
    ],
    "legbye": [
        "Deflected off the pad, running down to fine leg for a leg-bye.",
        "Loud appeal for LBW, but it hit the pad and ran away for a leg-bye."
    ],
    "wicket_bowled": [
        "OUT! Clean bowled! {batsman} misses, and the stumps are shattered. {bowler} strikes!",
        "OUT! Knocked him over! The ball nips back and clips the top of off stump. {batsman} has to walk."
    ],
    "wicket_caught": [
        "OUT! Caught! {batsman} goes for the big drive but edges it. Caught by {fielder} at second slip!",
        "OUT! Caught in the deep! {batsman} didn't get enough timing on the pull, caught by {fielder} at deep midwicket.",
        "OUT! Safe hands! {batsman} miscues the lofted shot and {fielder} takes an easy catch at mid-on."
    ],
    "wicket_lbw": [
        "OUT! LBW! Plumb! {bowler} appeals loudly, the umpire raises the finger. {batsman} is gone.",
        "OUT! LBW! {batsman} is struck on the pad, right in front of the stumps. Umpire's decision stands!"
    ],
    "wicket_runout": [
        "OUT! Run out! Chaos in the middle. {batsman} goes for a quick single but a brilliant throw from {fielder} hits the stumps!",
        "OUT! Run out! Direct hit! {batsman} is caught short of the crease. Brilliant fielding by {fielder}!"
    ],
    "wicket_stumped": [
        "OUT! Stumped! {batsman} charges down the crease, misses the turn, and the keeper whipped the bails off in a flash!",
        "OUT! Smart work by the keeper! {batsman} dragged his foot outside the crease, stumped by the keeper."
    ]
}