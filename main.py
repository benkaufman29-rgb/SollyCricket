import os
import sys
import time
import random
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from engine.models import MatchState, Team, BallOutcome
from engine.simulator import simulate_delivery

console = Console()

def create_layout(match_state: MatchState) -> Layout:
    """Creates the cricinfo-style terminal layout."""
    layout = Layout()
    
    # Split into header, body, and footer
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body", minimum_size=15),
        Layout(name="footer", size=3)
    )
    
    # Split body into scorecard (left) and commentary (right)
    layout["body"].split_row(
        Layout(name="scorecard", ratio=3),
        Layout(name="commentary", ratio=2)
    )
    
    return layout

def update_header(layout: Layout, match_state: MatchState):
    """Updates the header with the match summary banner."""
    innings = match_state.current_innings
    batting_team = innings.batting_team.name
    bowling_team = innings.bowling_team.name
    score_str = f"{innings.score}/{innings.wickets}"
    overs_str = f"({innings.overs_str} Ov)"
    
    # Calculate Run Rate
    overs_float = (innings.balls_bowled // 6) + (innings.balls_bowled % 6) / 6.0
    crr = innings.score / overs_float if overs_float > 0 else 0.0
    
    banner = Text()
    banner.append(f" {batting_team.upper()} vs {bowling_team.upper()} ", style="bold white on blue")
    banner.append("  |  ")
    banner.append(f"Score: {score_str} ", style="bold green" if innings.wickets < 10 else "bold red")
    banner.append(f"{overs_str}", style="italic cyan")
    banner.append("  |  ")
    banner.append(f"CRR: {crr:.2f}", style="yellow")
    
    if match_state.innings_number == 2:
        target = innings.target
        runs_needed = target - innings.score
        balls_remaining = (match_state.overs_limit * 6) - innings.balls_bowled if match_state.overs_limit else 999
        if runs_needed <= 0:
            banner.append("  |  ")
            banner.append("TARGET REACHED", style="bold green blink")
        else:
            banner.append("  |  ")
            banner.append(f"Need {runs_needed} runs off {balls_remaining} balls", style="bold magenta")
            
    header_panel = Panel(
        banner,
        title=f"Solly Cricket - Innings {match_state.innings_number}",
        title_align="left",
        border_style="blue"
    )
    layout["header"].update(header_panel)

def update_scorecard(layout: Layout, match_state: MatchState):
    """Renders the detailed batting and bowling scorecard table."""
    innings = match_state.current_innings
    
    # Batting Table
    bat_table = Table(title=f"Batting: {innings.batting_team.name}", expand=True, box=None)
    bat_table.add_column("Batsman", style="bold cyan", width=25)
    bat_table.add_column("Status", style="dim", width=35)
    bat_table.add_column("R", justify="right", style="bold green")
    bat_table.add_column("B", justify="right")
    bat_table.add_column("4s", justify="right")
    bat_table.add_column("6s", justify="right")
    bat_table.add_column("SR", justify="right", style="magenta")
    
    for player in innings.batting_team.players:
        status_desc = ""
        if player.status == "dnb":
            status_desc = "did not bat"
        elif player.status == "batting":
            is_striker = " *" if innings.striker == player else ""
            status_desc = f"batting{is_striker}"
        else:
            status_desc = player.dismissal or "out"
            
        # Highlight active batsman row
        row_style = "bold white" if player.status == "batting" else "dim" if player.status == "dnb" else "white"
        
        bat_table.add_row(
            player.name,
            status_desc,
            str(player.runs_scored) if player.status != "dnb" else "-",
            str(player.balls_faced) if player.status != "dnb" else "-",
            str(player.fours) if player.status != "dnb" else "-",
            str(player.sixes) if player.status != "dnb" else "-",
            f"{player.strike_rate:.1f}" if player.status != "dnb" else "-",
            style=row_style
        )
    
    # Extras row
    bat_table.add_row(
        "Extras",
        f"(w {innings.extras['wides']}, nb {innings.extras['noballs']}, b {innings.extras['byes']}, lb {innings.extras['legbyes']})",
        str(innings.total_extras),
        "", "", "", "",
        style="dim"
    )
    
    # Bowling Table
    bowl_table = Table(title=f"Bowling: {innings.bowling_team.name}", expand=True, box=None)
    bowl_table.add_column("Bowler", style="bold yellow", width=25)
    bowl_table.add_column("O", justify="right")
    bowl_table.add_column("M", justify="right")
    bowl_table.add_column("R", justify="right")
    bowl_table.add_column("W", justify="right", style="bold red")
    bowl_table.add_column("Econ", justify="right", style="magenta")
    
    for player in innings.bowling_team.players:
        # Show bowler stats if they have bowled a ball
        if player.balls_bowled > 0 or innings.current_bowler == player:
            is_current = " *" if innings.current_bowler == player else ""
            row_style = "bold white" if innings.current_bowler == player else "white"
            bowl_table.add_row(
                player.name + is_current,
                player.overs_bowled,
                str(player.maidens),
                str(player.runs_conceded),
                str(player.wickets_taken),
                f"{player.economy_rate:.2f}",
                style=row_style
            )
            
    # Combine lists inside a single panel
    scorecard_content = Layout()
    scorecard_content.split_column(
        Layout(bat_table, ratio=2),
        Layout(bowl_table, ratio=1)
    )
    
    layout["scorecard"].update(Panel(scorecard_content, title="Live Scorecard", border_style="cyan"))

def update_commentary(layout: Layout, match_state: MatchState):
    """Renders the scrollable ball-by-ball commentary feed."""
    innings = match_state.current_innings
    
    # Grab the last 8 outcomes for display
    recent_commentary = list(reversed(innings.commentary[-8:]))
    
    feed_text = Text()
    
    if not recent_commentary:
        feed_text.append("\n Waiting for the first ball to be bowled...", style="dim italic")
    else:
        for idx, outcome in enumerate(recent_commentary):
            # Calculate ball count in over format
            # Since recent_commentary is reversed, we need to map to correct over index or pull from outcomes list
            # We can associate a ball stamp with each outcome, or just show the index
            # Let's display the outcome's details
            
            # Format ball bubble
            bubble = Text()
            if outcome.is_wicket:
                bubble.append(" W ", style="bold white on red")
            elif outcome.extra_type:
                bubble.append(f" {outcome.extra_type.upper()} ", style="bold white on yellow")
            elif outcome.runs == 4:
                bubble.append(" 4 ", style="bold white on blue")
            elif outcome.runs == 6:
                bubble.append(" 6 ", style="bold white on purple")
            elif outcome.runs == 0:
                bubble.append(" 0 ", style="bold white on grey23")
            else:
                bubble.append(f" {outcome.runs} ", style="bold black on green")
                
            # Add line
            feed_text.append(f"\n ")
            feed_text.append(bubble)
            feed_text.append(f"  {outcome.batsman_name} to {outcome.bowler_name}: ", style="bold")
            feed_text.append(outcome.description)
            feed_text.append("\n" + "-"*50, style="dim")
            
    layout["commentary"].update(
        Panel(feed_text, title="Ball-by-Ball Commentary", border_style="green")
    )

def update_footer(layout: Layout, match_state: MatchState, autoplay=False):
    """Updates the footer with interactive prompt controls."""
    status = match_state.status_message
    prompt = "Press [ENTER] to bowl next ball, [A] to autoplay, or [Q] to quit"
    
    if autoplay:
        prompt = "Autoplay active... press [Ctrl+C] to pause"
    if match_state.current_innings.is_completed:
        if match_state.innings_number == 1:
            prompt = "Innings completed! Press [ENTER] to start 2nd Innings"
        else:
            prompt = "Match over! Press [Q] to quit or [R] to restart"
            
    footer_text = Text()
    footer_text.append(f"Status: {status}\n", style="bold yellow")
    footer_text.append(prompt, style="bold blink white")
    
    layout["footer"].update(Panel(footer_text, border_style="dim"))

def get_next_bowler(batting_team, bowling_team, current_bowler):
    """Picks a reasonable bowler to bowl the next over."""
    # Find all players classified as Bowlers or All-rounders, excluding the current bowler
    bowlers = [p for p in bowling_team.players if p.role in ["Bowler", "All-rounder"] and p != current_bowler]
    
    # Fallback to any player if needed
    if not bowlers:
        bowlers = [p for p in bowling_team.players if p != current_bowler]
        
    # Pick randomly from the available bowlers
    return random.choice(bowlers)

def main():
    # Load Australia and England squads
    try:
        aus_team = Team.from_json_file("data/squads/australia.json")
        eng_team = Team.from_json_file("data/squads/england.json")
    except Exception as e:
        console.print(f"[bold red]Error loading squads: {e}[/bold red]")
        sys.exit(1)
        
    # Match State Setup
    # Let's run a 20-over match simulation for quick gameplay
    match = MatchState(aus_team, eng_team, overs_limit=20)
    match.start_match()
    
    layout = create_layout(match)
    
    autoplay = False
    
    with Live(layout, refresh_per_second=4, screen=True) as live:
        while True:
            # 1. Update TUI components
            update_header(layout, match)
            update_scorecard(layout, match)
            update_commentary(layout, match)
            update_footer(layout, match, autoplay)
            
            # If autoplay is on and innings is active, simulate next ball with delay
            if autoplay and not match.current_innings.is_completed:
                time.sleep(0.8)
                
                # Check for over completion before simulating next ball (to choose bowler)
                innings = match.current_innings
                if innings.balls_bowled > 0 and innings.balls_bowled % 6 == 0 and innings.current_bowler.current_over_balls == 0:
                    # Select next bowler
                    next_bowler = get_next_bowler(innings.batting_team, innings.bowling_team, innings.current_bowler)
                    innings.change_bowler(next_bowler)
                    
                outcome = simulate_delivery(
                    innings.batting_team,
                    innings.bowling_team,
                    innings.striker,
                    innings.non_striker,
                    innings.current_bowler,
                )
                match.step_ball(outcome)
                continue
                
            # If match is finished, check keyboard input
            live.stop() # Temporarily stop live screen to prompt for standard input
            
            # Simple terminal prompt
            try:
                user_input = input().strip().lower()
            except KeyboardInterrupt:
                break
                
            live.start() # Restart live display
            
            if user_input == 'q':
                break
            elif user_input == 'a':
                autoplay = True
            elif user_input == 'r' and match.innings2 and match.innings2.is_completed:
                # Restart match
                match = MatchState(aus_team, eng_team, overs_limit=20)
                match.start_match()
                autoplay = False
            elif match.current_innings.is_completed:
                if match.innings_number == 1:
                    match.start_second_innings()
                    autoplay = False
                else:
                    # Match finished, waiting for 'q' or 'r'
                    pass
            else:
                # Simulate next delivery manually
                innings = match.current_innings
                
                # If over is complete, select next bowler before next ball
                if innings.balls_bowled > 0 and innings.balls_bowled % 6 == 0 and innings.current_bowler.current_over_balls == 0:
                    next_bowler = get_next_bowler(innings.batting_team, innings.bowling_team, innings.current_bowler)
                    innings.change_bowler(next_bowler)
                    
                outcome = simulate_delivery(
                    innings.batting_team,
                    innings.bowling_team,
                    innings.striker,
                    innings.non_striker,
                    innings.current_bowler,
                )
                match.step_ball(outcome)

if __name__ == "__main__":
    main()
