"""Read information from Github API using GraphQL GitHubAPI."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import typer

from public import public

from ghreport.config import ArgsCLI
from ghreport.report import GHReport

__all__ = ['app', 'main']


def _start_default() -> date:
    start_day_threshold = 25
    today = date.today()
    return (
        today.replace(day=1)
        if today.day >= start_day_threshold
        else (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    )


def _end_default(start: date) -> date:
    return (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)


start_def = _start_default()
end_def = _end_default(start_def)

app = typer.Typer(
    add_help_option=True,
    help='Generate Markdown reports from GitHub issues and PRs.',
)


@public
@app.callback(invoke_without_command=True)
def main(
    start_date: str = typer.Option(
        start_def.strftime('%Y-%m-%d'),
        '--start-date',
        help='Specify the start date filter (YYYY-MM-DD).',
    ),
    end_date: str = typer.Option(
        end_def.strftime('%Y-%m-%d'),
        '--end-date',
        help='Specify the end date filter (YYYY-MM-DD).',
    ),
    gh_token: str = typer.Option(
        '', '--gh-token', help='Specify the GitHub access token.'
    ),
    config_file: Path = typer.Option(
        Path('.ghreport.yaml'),
        '--config-file',
        help='Path to config file; defaults to ./.ghreport.yaml',
    ),
) -> None:
    """Run the report generation with the provided options."""
    args = ArgsCLI(
        start_date=start_date,
        end_date=end_date,
        gh_token=gh_token,
        config_file=str(config_file),
    )
    GHReport(args).run()
