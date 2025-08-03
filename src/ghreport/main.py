#!/usr/bin/env python
"""
Read information from Github API using GraphQL GitHubAPI.
"""

from ghreport.cli import parse_cli
from ghreport.config import ArgsCLI
from ghreport.report import GHReport


def main() -> None:
    parsed_args = parse_cli().parse_args()
    raw_args = dict(parsed_args._get_kwargs())
    report = GHReport(ArgsCLI(**raw_args))
    report.run()


if __name__ == '__main__':
    main()
