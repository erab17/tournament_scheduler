# Tournament Scheduler

This Flask application generates tournament schedules for ice hockey teams, ensuring constraints like match concurrency, game timing, and long breaks are met. It uses OR-Tools for constraint programming to optimize the schedule.

## Features
- Dynamic input for clubs and teams
- Constraints for match concurrency and timing
- Long breaks for ice maintenance
- Feasibility checks and schedule suggestions
- Restricted club matchups

## Setup
1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd tournament_scheduler