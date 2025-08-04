from __future__ import annotations

import logging

from pathlib import Path

import pandas as pd

from jinja2 import Template

from ghreport.config import Config

__all__ = ['GHReportGenerator']


class GHReportGenerator:
    """Generate a Markdown report summarising GitHub issues and PRs.

    Parameters
    ----------
    config
        Parsed CLI configuration holding repos, authors, dates, and paths.
    """

    date_cols: tuple[str, ...] = (
        'created_at',
        'closed_at',
        'merged_at',
        'updated_at',
        'last_edit_at',
    )

    def __init__(self, config: Config) -> None:
        self.config = config
        self._root = Path(__file__).resolve().parent
        self.logger = logging.getLogger(__name__)

    def get_output_filepath_from_args(self, extension: str) -> Path:
        args = self.config.args
        fname = (
            f'report-{self.config.name}-'
            f'{args.start_date.replace("-", "")}-'
            f'{args.end_date.replace("-", "")}.{extension}'
        )
        return Path(self.config.output_dir) / fname

    def generate(self, results: pd.DataFrame) -> None:
        tmpl = self._load_template()
        prepared = self._prepare_dataframe(results)
        projects = self._build_tables(prepared)
        self._write_markdown(tmpl, projects)

    def _load_template(self) -> Template:
        path = self._root / 'templates' / 'template.md'
        with path.open(encoding='utf-8') as fh:
            return Template(fh.read())

    def _write_markdown(
        self, tmpl: Template, projects: list[dict[str, str]]
    ) -> None:
        path = self.get_output_filepath_from_args('md')
        path.parent.mkdir(parents=True, exist_ok=True)

        args = self.config.args
        authors_display = [next(iter(a), '') for a in self.config.authors]

        content = tmpl.render(
            report_title=self.config.title or 'Report',
            orgs_repos=', '.join(self.config.repos),
            authors=', '.join(authors_display),
            start_date=args.start_date,
            end_date=args.end_date,
            projects=projects,
        )
        path.write_text(content, encoding='utf-8')
        self.logger.info('Markdown report saved to %s', path)

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # truncate date columns to YYYY-MM-DD
        existing_dates = [c for c in self.date_cols if c in df.columns]
        if existing_dates:
            df[existing_dates] = df[existing_dates].apply(
                lambda col: col.astype(str).str.slice(0, 10)
            )

        # turn issue/PR number into an HTML link
        df['number'] = (
            "<a href='" + df['url'] + "'>" + df['number'].astype(str) + '</a>'
        )

        # merge / state normalisation for PRs
        is_pr = df['type'] == 'pr'
        merged_mask = df['labels_raw'].str.contains('Merged', na=False)

        df.loc[is_pr, 'merged_at'] = df.loc[is_pr].apply(
            lambda s: s['merged_at']
            or (s['closed_at'] if merged_mask.loc[s.name] else None),
            axis=1,
        )
        df.loc[is_pr, 'state'] = df.loc[is_pr].apply(
            lambda s: s['state']
            if s['state'] != 'CLOSED'
            else ('MERGED' if merged_mask.loc[s.name] else s['closed_at']),
            axis=1,
        )

        # map GitHub username -> real name
        gh_users = {
            k: v for author in self.config.authors for k, v in author.items()
        }
        df['author_or_assignees'] = df['author_or_assignees'].map(
            lambda u: gh_users.get(u, u)
        )
        df['author'] = df['author_or_assignees']
        df['assignees'] = df['author_or_assignees']

        return df

    def _output_columns(self) -> list[str]:
        base = [
            'repo_name',
            'number',
            'title',
            'author',
            'assignees',
            'labels',
            'state',
        ]
        return [*base, *self.date_cols]

    def _issues_columns(self, cols: list[str]) -> list[str]:
        prs_only = {
            'created_at',
            'merged_at',
            'updated_at',
            'last_edit_at',
            'author',
        }
        return [c for c in cols if c not in prs_only]

    def _prs_columns(self, cols: list[str]) -> list[str]:
        issues_only = {
            'closed_at',
            'created_at',
            'updated_at',
            'last_edit_at',
            'assignees',
        }
        return [c for c in cols if c not in issues_only]

    def _build_tables(self, df: pd.DataFrame) -> list[dict[str, str]]:
        cols = self._output_columns()
        issues_cols = self._issues_columns(cols)
        prs_cols = self._prs_columns(cols)

        projects: list[dict[str, str]] = []
        for repo in self.config.repos:
            subset = df[df.org_repo == repo]
            prs_md_df = subset[subset.type == 'pr'][prs_cols].reset_index(
                drop=True
            )
            issues_md_df = subset[subset.type == 'issue'][
                issues_cols
            ].reset_index(drop=True)

            projects.append(
                {
                    'name': repo.split('/')[1],
                    'pr_results': prs_md_df.to_markdown(index=False)
                    if not prs_md_df.empty
                    else 'None',
                    'issue_results': issues_md_df.to_markdown(index=False)
                    if not issues_md_df.empty
                    else 'None',
                }
            )
        return projects
