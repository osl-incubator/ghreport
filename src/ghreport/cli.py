"""
Read information from Github API using GraphQL GitHubAPI.
"""

import argparse

from datetime import date, timedelta
from pathlib import Path

from public import public


def get_default_start_date() -> date:
    current_date = date.today()
    month_day_limit = 25
    if current_date.day >= month_day_limit:
        # If the current day is greater or equal to 25, use the
        # current month for the report
        start_date_default = current_date.replace(day=1)
    else:
        start_date_default = (
            current_date.replace(day=1) - timedelta(days=1)
        ).replace(day=1)
    return start_date_default


def get_default_end_date(start_date_default: date) -> date:
    return (start_date_default + timedelta(days=32)).replace(
        day=1
    ) - timedelta(days=1)


@public
def parse_cli() -> argparse.ArgumentParser:
    # todo: check if it is necessary
    # load_environment_variables()

    start_date_default = get_default_start_date()
    end_date_default = get_default_end_date(start_date_default)

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--start-date',
        dest='start_date',
        action='store',
        type=str,
        default=start_date_default.strftime('%Y-%m-%d'),
        help='Specify the start date filter (YYYY-MM-DD).',
    )
    parser.add_argument(
        '--end-date',
        dest='end_date',
        action='store',
        type=str,
        default=end_date_default.strftime('%Y-%m-%d'),
        help='Specify the end date filter (YYYY-MM-DD).',
    )
    parser.add_argument(
        '--gh-token',
        dest='gh_token',
        action='store',
        type=str,
        default='',
        help='Specify the GitHub access token.',
    )
    parser.add_argument(
        '--config-file',
        dest='config_file',
        action='store',
        type=str,
        default=str(Path(__file__).parent / '.ghreport.yaml'),
        help='Specify the GitHub access token.',
    )

    return parser
