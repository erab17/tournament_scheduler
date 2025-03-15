from flask import Blueprint, render_template, request
from app.utils import parse_time, format_time, calculate_statistics, generate_and_schedule_matchups
import statistics

# Define the main blueprint
main = Blueprint('main', __name__)

@main.route('/', methods=['GET', 'POST'])
def index():
    stats = None
    club_count = 1
    form_data = {}
    restricted_clubs = set()
    long_break_time = 25  # Default value
    long_break_frequency = 4  # Default value
    game_scheduling_strategy = 'random'  # Default value
    max_consecutive_games = 2  # Default value
    max_rest_games = 2  # Default value
    max_wait_time = 60  # Default value

    # Load existing restricted clubs from form
    if 'restricted_clubs' in request.form:
        restricted_clubs = set(eval(request.form['restricted_clubs'])) if request.form['restricted_clubs'] else set()

    if request.method == 'POST':
        form_data = request.form
        clubs = {}
        for key, value in request.form.items():
            if key.startswith('club_name_') and value:
                idx = key.split('_')[-1]
                num_teams = int(request.form.get(f'num_teams_{idx}', 0))
                clubs[value] = [f"{value}{i+1}" for i in range(num_teams)]
                club_count = max(club_count, int(idx) + 1)

        # Handle adding club restrictions
        if 'add_restriction' in request.form:
            club1 = request.form.get('restrict_club1')
            club2 = request.form.get('restrict_club2')
            if club1 and club2 and club1 != club2:
                restricted_clubs.add((club1, club2))

        # Extract form data
        matches_per_team = int(request.form['matches_per_team'])
        concurrency = min(int(request.form['concurrency']), 4)
        game_time = int(request.form['game_time'])
        break_time = int(request.form['break_time'])
        spread_games = request.form.get('spread_games') == 'yes'
        start_time = parse_time(request.form['start_time'])
        force_max_concurrency = request.form.get('force_max_concurrency') == 'yes'
        allow_more_matches = request.form.get('allow_more_matches') == 'yes'
        home_club = request.form.get('home_club', '')
        long_break_time = int(request.form.get('long_break_time', 25))
        long_break_frequency = int(request.form.get('long_break_frequency', 4))
        game_scheduling_strategy = request.form.get('game_scheduling_strategy', 'random')
        max_consecutive_games = int(request.form.get('max_consecutive_games', 2))
        max_rest_games = int(request.form.get('max_rest_games', 2))
        max_wait_time = int(request.form.get('max_wait_time', 60))

        if 'preview' in request.form:
            # Preview statistics
            stats = calculate_statistics(clubs, matches_per_team, concurrency, force_max_concurrency, allow_more_matches)
            return render_template(
                'index.html',
                stats=stats,
                club_count=club_count,
                form_data=form_data,
                clubs=list(clubs.keys()),
                restricted_clubs=restricted_clubs,
                long_break_time=long_break_time,
                long_break_frequency=long_break_frequency,
                game_scheduling_strategy=game_scheduling_strategy,
                max_consecutive_games=max_consecutive_games,
                max_rest_games=max_rest_games,
                max_wait_time=max_wait_time
            )
        elif 'generate' in request.form:
            # Generate and schedule matchups
            schedule, warnings, team_games, team_opponents, team_timing_stats, teams = generate_and_schedule_matchups(
                clubs, matches_per_team, concurrency, game_time, break_time, spread_games, start_time,
                force_max_concurrency, allow_more_matches, home_club, restricted_clubs,
                long_break_time, long_break_frequency, game_scheduling_strategy,
                max_consecutive_games, max_rest_games, max_wait_time
            )

            # Calculate average timing stats
            teams_with_two_or_more = [
                t for t in teams
                if t in team_games and team_games[t] >= 2 and team_timing_stats[t]['first_match'] is not None
            ]
            teams_with_one_or_more = [
                t for t in teams
                if t in team_games and team_games[t] >= 1 and team_timing_stats[t]['first_match'] is not None
            ]

            avg_min_time = (statistics.mean([team_timing_stats[t]['min_time_between']
                                           for t in teams_with_two_or_more
                                           if team_timing_stats[t]['min_time_between'] is not None])
                           if teams_with_two_or_more else None)
            avg_max_time = (statistics.mean([team_timing_stats[t]['max_time_between']
                                           for t in teams_with_two_or_more
                                           if team_timing_stats[t]['max_time_between'] is not None])
                           if teams_with_two_or_more else None)
            avg_median_time = (statistics.mean([team_timing_stats[t]['median_time_between']
                                              for t in teams_with_two_or_more
                                              if team_timing_stats[t]['median_time_between'] is not None])
                              if teams_with_two_or_more else None)
            avg_max_consecutive = (statistics.mean([team_timing_stats[t]['max_consecutive_matches']
                                                  for t in teams_with_one_or_more])
                                  if teams_with_one_or_more else None)

            return render_template(
                'result.html',
                schedule=schedule,
                warnings=warnings,
                team_games=team_games,
                team_opponents=team_opponents,
                team_timing_stats=team_timing_stats,
                format_time=format_time,
                analysis=len(schedule) == 0,
                request=request,
                avg_min_time=avg_min_time,
                avg_max_time=avg_max_time,
                avg_median_time=avg_median_time,
                avg_max_consecutive=avg_max_consecutive,
                long_break_time=long_break_time,
                long_break_frequency=long_break_frequency,
                game_scheduling_strategy=game_scheduling_strategy,
                max_consecutive_games=max_consecutive_games,
                max_rest_games=max_rest_games,
                max_wait_time=max_wait_time
            )

    return render_template('index.html', stats=stats, club_count=club_count, form_data=form_data,
                         clubs=list(clubs.keys()) if 'clubs' in locals() else [],
                         restricted_clubs=restricted_clubs,
                         long_break_time=long_break_time,
                         long_break_frequency=long_break_frequency,
                         game_scheduling_strategy=game_scheduling_strategy,
                         max_consecutive_games=max_consecutive_games,
                         max_rest_games=max_rest_games,
                         max_wait_time=max_wait_time)