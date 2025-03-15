from datetime import datetime, timedelta
import itertools
import math
from ortools.sat.python import cp_model
import statistics

def parse_time(time_str):
    """Parse a time string in HH:MM format into a datetime object."""
    return datetime.strptime(time_str, "%H:%M")

def format_time(dt):
    """Format a datetime object into a HH:MM string."""
    return dt.strftime("%H:%M")

def calculate_statistics(clubs, matches_per_team, concurrency, force_max_concurrency, allow_more_matches):
    """Calculate feasibility and statistics for the tournament."""
    teams = [(club, team) for club, teams in clubs.items() for team in teams]
    all_possible_matchups = [(t1, t2) for t1, t2 in itertools.combinations(teams, 2) if t1[0] != t2[0]]

    total_teams = len(teams)
    total_possible_matchups = len(all_possible_matchups)
    total_required_matches = total_teams * matches_per_team / 2
    max_possible_concurrency = total_teams // 2
    effective_concurrency = min(concurrency, max_possible_concurrency)
    min_slots_needed = math.ceil(total_required_matches / effective_concurrency)

    is_integer_matches = total_required_matches.is_integer()
    is_feasible = (allow_more_matches or is_integer_matches) and total_required_matches <= total_possible_matchups

    concurrency_message = ""
    if concurrency > max_possible_concurrency:
        concurrency_message = (f"Requested concurrency ({concurrency}) exceeds maximum possible "
                             f"({max_possible_concurrency}) with {total_teams} teams. Adjusted to {effective_concurrency}.")
        if force_max_concurrency:
            concurrency_message += f" With 'Force Max Concurrency' enabled, all used slots will have {effective_concurrency} matches."
        else:
            concurrency_message += f" Without forcing, slots aim for up to {effective_concurrency} matches, prioritized early."

    feasibility_message = "Possible" if is_feasible else (
        f"Not possible: Total matches ({total_required_matches}) must be an integer unless 'Allow More Matches' is enabled."
        if not is_integer_matches else f"Not possible with exactly {matches_per_team} matches per team."
    )

    suggestion = ""
    if not is_feasible:
        if not is_integer_matches:
            lower_matches = math.floor(total_required_matches) * 2 / total_teams
            upper_matches = math.ceil(total_required_matches) * 2 / total_teams
            suggestion = f"Enable 'Allow More Matches' or adjust matches per team to {int(lower_matches)} or {int(upper_matches)} for an integer total."
        elif total_required_matches > total_possible_matchups:
            suggestion = f"Reduce matches per team to {int(2 * total_possible_matchups / total_teams)} or add more teams."

    return {
        'total_teams': total_teams,
        'total_possible_matchups': total_possible_matchups,
        'total_required_matches': total_required_matches,
        'min_slots_needed': min_slots_needed,
        'is_feasible': is_feasible,
        'feasibility_message': feasibility_message,
        'suggestion': suggestion,
        'concurrency_message': concurrency_message
    }

def generate_and_schedule_matchups(clubs, matches_per_team, concurrency, game_time, break_time, spread_games, start_time,
                                   force_max_concurrency, allow_more_matches, home_club, restricted_clubs,
                                   long_break_time, long_break_frequency, game_scheduling_strategy,
                                   max_consecutive_games, max_rest_games, max_wait_time):
    """Generate and schedule tournament matchups using constraint programming."""
    if restricted_clubs is None:
        restricted_clubs = set()

    teams = [(club, team) for club, teams in clubs.items() for team in teams]
    all_possible_matchups = [(t1, t2) for t1, t2 in itertools.combinations(teams, 2) if t1[0] != t2[0]]
    allowed_matchups = [m for m in all_possible_matchups if not ((m[0][0], m[1][0]) in restricted_clubs or (m[1][0], m[0][0]) in restricted_clubs)]

    total_teams = len(teams)
    max_possible_concurrency = total_teams // 2
    effective_concurrency = min(concurrency, max_possible_concurrency)
    total_required_matches = total_teams * matches_per_team / 2

    model = cp_model.CpModel()
    solver = cp_model.CpSolver()

    num_slots = math.ceil(total_required_matches / effective_concurrency) + 4
    matchup_slot = {m: model.NewIntVar(-1, num_slots - 1, f"matchup_{m}") for m in range(len(allowed_matchups))}
    matchup_used = {m: model.NewBoolVar(f"used_{m}") for m in range(len(allowed_matchups))}

    for m in matchup_used:
        model.Add(matchup_slot[m] >= 0).OnlyEnforceIf(matchup_used[m])
        model.Add(matchup_slot[m] == -1).OnlyEnforceIf(matchup_used[m].Not())

    team_matches = {team: [] for team in teams}
    for m, (t1, t2) in enumerate(allowed_matchups):
        team_matches[t1].append(m)
        team_matches[t2].append(m)

    home_teams = [team for team in teams if team[0] == home_club]
    away_teams = [team for team in teams if team[0] != home_club]
    has_extra = {}

    if allow_more_matches:
        if home_club:
            for team in home_teams:
                match_sum = sum(matchup_used[m] for m in team_matches[team])
                model.Add(match_sum == matches_per_team)
            for team in away_teams:
                match_sum = sum(matchup_used[m] for m in team_matches[team])
                has_extra[team] = model.NewBoolVar(f"has_extra_{team}")
                model.Add(match_sum >= matches_per_team)
                model.Add(match_sum <= matches_per_team + 1)
        else:
            for team in teams:
                match_sum = sum(matchup_used[m] for m in team_matches[team])
                has_extra[team] = model.NewBoolVar(f"has_extra_{team}")
                model.Add(match_sum >= matches_per_team)
                model.Add(match_sum <= matches_per_team + 1)
    else:
        for team in teams:
            match_sum = sum(matchup_used[m] for m in team_matches[team])
            model.Add(match_sum == matches_per_team)

    slot_counts = []
    slot_used = []
    for slot in range(num_slots):
        slot_matches = []
        for m, (t1, t2) in enumerate(allowed_matchups):
            is_in_slot = model.NewBoolVar(f"slot_{slot}_{m}")
            model.Add(matchup_slot[m] == slot).OnlyEnforceIf(is_in_slot)
            model.Add(matchup_slot[m] != slot).OnlyEnforceIf(is_in_slot.Not())
            slot_matches.append(is_in_slot)

        count = model.NewIntVar(0, effective_concurrency, f"slot_count_{slot}")
        used = model.NewBoolVar(f"slot_used_{slot}")
        model.Add(count == sum(slot_matches))
        model.Add(count > 0).OnlyEnforceIf(used)
        model.Add(count == 0).OnlyEnforceIf(used.Not())
        slot_counts.append(count)
        slot_used.append(used)

        for team in teams:
            team_slot_matches = [slot_matches[m] for m in team_matches[team]]
            model.Add(sum(team_slot_matches) <= 1)

    if force_max_concurrency:
        for slot in range(num_slots):
            model.Add(slot_counts[slot] == effective_concurrency).OnlyEnforceIf(slot_used[slot])
        for slot in range(num_slots - 1):
            model.Add(slot_used[slot + 1] <= slot_used[slot])

    total_matches = sum(matchup_used[m] for m in range(len(allowed_matchups)))
    if allow_more_matches:
        model.Add(total_matches >= int(total_required_matches))
    else:
        model.Add(total_matches == int(total_required_matches))

    slot_penalty = sum(slot * slot_counts[slot] for slot in range(num_slots))
    max_slot = model.NewIntVar(0, num_slots - 1, "max_slot")
    for m in matchup_slot:
        model.Add(max_slot >= matchup_slot[m])
    model.Minimize(slot_penalty + 1000 * max_slot)

    # Add max wait time constraints
    slot_duration = game_time + (break_time if spread_games else 0)
    for team in teams:
        team_matchups = team_matches[team]
        if len(team_matchups) >= 2:
            # For each pair of consecutive matches for this team
            for i, j in itertools.combinations(team_matchups, 2):
                # Create an ordering variable
                i_before_j = model.NewBoolVar(f"match_{i}_before_{j}")
                
                # Create a variable to check if both matchups are used
                both_used = model.NewBoolVar(f"both_used_{i}_{j}")
                model.AddBoolAnd([matchup_used[i], matchup_used[j]]).OnlyEnforceIf(both_used)
                model.AddBoolOr([matchup_used[i].Not(), matchup_used[j].Not()]).OnlyEnforceIf(both_used.Not())
                
                # Enforce ordering only if both matchups are used
                model.Add(matchup_slot[i] < matchup_slot[j]).OnlyEnforceIf([both_used, i_before_j])
                model.Add(matchup_slot[j] < matchup_slot[i]).OnlyEnforceIf([both_used, i_before_j.Not()])
                
                # If i is before j and both are used, constrain wait time
                wait_slots = model.NewIntVar(0, num_slots, f"wait_slots_{i}_{j}")
                model.Add(wait_slots == matchup_slot[j] - matchup_slot[i]).OnlyEnforceIf([both_used, i_before_j])
                
                # Convert slots to minutes
                wait_minutes = model.NewIntVar(0, num_slots * slot_duration, f"wait_minutes_{i}_{j}")
                model.Add(wait_minutes == wait_slots * slot_duration).OnlyEnforceIf([both_used, i_before_j])
                
                # Consider long breaks
                if long_break_frequency > 0:
                    # Pre-calculate max possible breaks as a Python integer
                    max_breaks = num_slots // long_break_frequency
                    
                    # Calculate number of long breaks between i and j
                    breaks_between = model.NewIntVar(0, max_breaks, f"breaks_between_{i}_{j}")
                    
                    # Use AddDivisionEquality for the division operation
                    temp_div_result = model.NewIntVar(0, num_slots, f"temp_div_{i}_{j}")
                    model.AddDivisionEquality(temp_div_result, wait_slots, long_break_frequency)
                    model.Add(breaks_between <= temp_div_result).OnlyEnforceIf([both_used, i_before_j])
                    
                    # Adjust wait time calculation with long breaks
                    adjusted_wait = model.NewIntVar(0, num_slots * slot_duration + num_slots * long_break_time, 
                                                    f"adjusted_wait_{i}_{j}")
                    model.Add(adjusted_wait == wait_minutes + breaks_between * (long_break_time - break_time)).OnlyEnforceIf([both_used, i_before_j])
                    
                    # Apply max wait constraint with adjusted time
                    model.Add(adjusted_wait <= max_wait_time).OnlyEnforceIf([both_used, i_before_j])
                else:
                    # Apply max wait constraint without extra long breaks
                    model.Add(wait_minutes <= max_wait_time).OnlyEnforceIf([both_used, i_before_j])
                
                # Same constraints for j before i
                wait_slots_rev = model.NewIntVar(0, num_slots, f"wait_slots_rev_{i}_{j}")
                model.Add(wait_slots_rev == matchup_slot[i] - matchup_slot[j]).OnlyEnforceIf([both_used, i_before_j.Not()])
                
                wait_minutes_rev = model.NewIntVar(0, num_slots * slot_duration, f"wait_minutes_rev_{i}_{j}")
                model.Add(wait_minutes_rev == wait_slots_rev * slot_duration).OnlyEnforceIf([both_used, i_before_j.Not()])
                
                if long_break_frequency > 0:
                    # Use the same pre-calculated max breaks value
                    breaks_between_rev = model.NewIntVar(0, max_breaks, 
                                                         f"breaks_between_rev_{i}_{j}")
                    
                    # Use AddDivisionEquality here too
                    temp_div_result_rev = model.NewIntVar(0, num_slots, f"temp_div_rev_{i}_{j}")
                    model.AddDivisionEquality(temp_div_result_rev, wait_slots_rev, long_break_frequency)
                    model.Add(breaks_between_rev <= temp_div_result_rev).OnlyEnforceIf([both_used, i_before_j.Not()])
                    
                    adjusted_wait_rev = model.NewIntVar(0, num_slots * slot_duration + num_slots * long_break_time, 
                                                        f"adjusted_wait_rev_{i}_{j}")
                    model.Add(adjusted_wait_rev == wait_minutes_rev + breaks_between_rev * (long_break_time - break_time)).OnlyEnforceIf([both_used, i_before_j.Not()])
                    
                    model.Add(adjusted_wait_rev <= max_wait_time).OnlyEnforceIf([both_used, i_before_j.Not()])
                else:
                    # Apply max wait constraint without extra long breaks (reverse)
                    model.Add(wait_minutes_rev <= max_wait_time).OnlyEnforceIf([both_used, i_before_j.Not()])

    status = solver.Solve(model)
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return [], [f"No feasible schedule found. Solver status: {status}"], {}, {}, {}, teams

    schedule = []
    current_time = start_time
    slot_assignments = {s: [] for s in range(num_slots)}
    team_match_times = {team: [] for team in teams}

    for m, (t1, t2) in enumerate(allowed_matchups):
        slot = solver.Value(matchup_slot[m])
        if slot >= 0:
            slot_assignments[slot].append((t1, t2))

    for slot in range(num_slots):
        if slot_assignments[slot]:
            match_time = current_time
            schedule.append((match_time, slot_assignments[slot]))
            for (c1, t1), (c2, t2) in slot_assignments[slot]:
                team_match_times[(c1, t1)].append(match_time)
                team_match_times[(c2, t2)].append(match_time)
            delta = game_time + (break_time if spread_games else 0)
            current_time += timedelta(minutes=delta)
            if long_break_frequency > 0 and (slot + 1) % long_break_frequency == 0 and slot < num_slots - 1:
                current_time += timedelta(minutes=long_break_time)

    team_games = {team: 0 for team in teams}
    team_opponents = {team: set() for team in teams}
    for slot in slot_assignments.values():
        for (c1, t1), (c2, t2) in slot:
            team_games[(c1, t1)] += 1
            team_games[(c2, t2)] += 1
            team_opponents[(c1, t1)].add(t2)
            team_opponents[(c2, t2)].add(t1)
    team_opponents = {team: list(opps) for team, opps in team_opponents.items()}

    team_timing_stats = {
        team: {
            'first_match': None,
            'last_match': None,
            'min_time_between': None,
            'max_time_between': None,
            'median_time_between': None,
            'max_consecutive_matches': 0
        } for team in teams
    }

    for team, times in team_match_times.items():
        if times:
            times_sorted = sorted(times)
            time_diffs = [(times_sorted[i+1] - times_sorted[i]).total_seconds() / 60
                         for i in range(len(times_sorted)-1)]

            slot_times = sorted(set(times_sorted))
            consecutive_count = 1
            max_consecutive = 1
            slot_duration = game_time + (break_time if spread_games else 0)
            for i in range(1, len(slot_times)):
                if (slot_times[i] - slot_times[i-1]).total_seconds() / 60 == slot_duration:
                    consecutive_count += 1
                    max_consecutive = max(max_consecutive, consecutive_count)
                else:
                    consecutive_count = 1

            team_timing_stats[team] = {
                'first_match': times_sorted[0],
                'last_match': times_sorted[-1],
                'min_time_between': min(time_diffs) if time_diffs else None,
                'max_time_between': max(time_diffs) if time_diffs else None,
                'median_time_between': statistics.median(time_diffs) if time_diffs else None,
                'max_consecutive_matches': max_consecutive
            }

    warnings = []
    used_slots = len([s for s in slot_assignments if slot_assignments[s]])
    if long_break_frequency > 0 and used_slots > 1 and used_slots % long_break_frequency == 1:
        warnings.append(f"Warning: Only one slot remains after the last long break (frequency: {long_break_frequency}). Consider adjusting the frequency.")
    if force_max_concurrency:
        warnings.append(f"Forced {effective_concurrency} concurrent matches per slot for all used slots.")
    if allow_more_matches:
        warnings.append("Allowed some teams to play more matches than specified to ensure a feasible schedule.")
    if home_club:
        warnings.append(f"Home club set to {home_club}; extra matches prioritized for away teams where possible.")
    if effective_concurrency < concurrency:
        warnings.append(f"Adjusted concurrency to {effective_concurrency} (maximum possible with {total_teams} teams).")

    for team, count in team_games.items():
        if count != matches_per_team:
            warnings.append(f"Team {team[1]} (Club {team[0]}) has {count} matches, expected {matches_per_team}.")

    if restricted_clubs:
        warnings.append(f"Restricted matches between: {', '.join([f'{c1} vs {c2}' for c1, c2 in restricted_clubs])}")

    return schedule, warnings, team_games, team_opponents, team_timing_stats, teams