from __future__ import annotations

import dataclasses
import re

from pathlib import Path
from typing import Any, cast

import pandas as pd

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from jinja2 import Template
from public import public

from ghreport.config import ArgsCLI, Config

__all__ = ['GHReportReader']


class _GitHubClient:
    def __init__(self, token: str) -> None:
        headers = {'Authorization': f'bearer {token}'}
        self.transport = AIOHTTPTransport(
            url='https://api.github.com/graphql', headers=headers
        )


@dataclasses.dataclass
class GitHubSearchFilters:
    org_repos: list[str]
    authors: list[str]
    search_type: str = 'pr'  # "pr" or "issue"
    start_date: str = ''
    end_date: str = ''
    status: list[str] = dataclasses.field(default_factory=list)
    merged_at: bool = False
    closed_at: bool = False
    updated_at: bool = False
    custom_filter: dict[str, str] = dataclasses.field(default_factory=dict)


class _GitHubSearch:
    _tmpl_path = (
        Path(__file__).with_suffix('').parent / 'templates' / 'search.graphql'
    )
    _selector_re = re.compile(r'#\s*\[(?P<left>[^\]=]+)==(?P<right>[^\]]+)\]')
    _page_limit: int = 100

    def __init__(self, token: str) -> None:
        self.client = _GitHubClient(token)
        self._template = Template(self._tmpl_path.read_text(encoding='utf-8'))

    @staticmethod
    def _conditional_include(line: str, ctx: dict[str, str]) -> bool:
        m = _GitHubSearch._selector_re.search(line)
        if not m:
            return True
        left, right = m.group('left').strip(), m.group('right').strip()
        # both operands expected to be identifiers present in ctx
        return ctx.get(left, '') == ctx.get(right, '')

    def _render_query(self, variables: dict[str, str]) -> str:
        raw = self._template.render(**variables)
        filtered: list[str] = []
        for line in raw.splitlines():
            if self._conditional_include(line, variables):
                filtered.append(line.split('#')[0])
        return '\n'.join(filtered)

    async def _fetch(
        self, query_str: str, vars_: dict[str, Any]
    ) -> dict[str, Any]:
        async with Client(
            transport=self.client.transport, fetch_schema_from_transport=False
        ) as session:
            query = gql(query_str)
            return cast(
                dict[str, Any],
                await session.execute(query, variable_values=vars_),
            )

    async def _paginate(
        self, variables: dict[str, str]
    ) -> list[dict[str, Any]]:
        after: str | None = None
        edges: list[dict[str, Any]] = []
        while True:
            page_vars = {
                **variables,
                'after': f', after: "{after}"' if after else '',
            }
            query_str = self._render_query(page_vars)
            exec_vars = {'first': self._page_limit}
            result = await self._fetch(query_str, exec_vars)
            batch = result.get('search', {}).get('edges', [])
            edges.extend(batch)
            info = result.get('search', {}).get('pageInfo', {})
            if not info.get('hasNextPage'):
                break
            after = info.get('endCursor')
        return edges

    def _extract_period(self, fld: str, flt: GitHubSearchFilters) -> str:
        return f'{fld}:{flt.start_date}..{flt.end_date}'

    async def search(self, flt: GitHubSearchFilters) -> pd.DataFrame:
        if flt.search_type not in {'pr', 'issue'}:
            raise ValueError("search_type must be 'pr' or 'issue'")

        node_type = 'PullRequest' if flt.search_type == 'pr' else 'Issue'

        vars_: dict[str, str] = {
            'org_repos': ' '.join(f'repo:{r}' for r in flt.org_repos),
            'gql_node_type': node_type,
            'search_type': flt.search_type,
            'status': ' '.join(f'is:{s}' for s in flt.status),
            'merged': (
                self._extract_period('merged', flt) if flt.merged_at else ''
            ),
            'closed': (
                self._extract_period('closed', flt) if flt.closed_at else ''
            ),
            'updated': (
                self._extract_period('updated', flt) if flt.updated_at else ''
            ),
            'custom_filter': ' '.join(
                f'{k}:{v}' for k, v in flt.custom_filter.items()
            ),
            'author': (
                ' '.join(f'author:{a}' for a in flt.authors)
                if flt.search_type == 'pr'
                else ''
            ),
            'assignee': (
                ' '.join(f'assignee:{a}' for a in flt.authors)
                if flt.search_type == 'issue'
                else ''
            ),
        }

        edges = await self._paginate(vars_)
        df = self._edges_to_df(edges)
        df['type'] = flt.search_type
        return df

    @staticmethod
    def _edges_to_df(edges: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for edge in edges:
            node = edge.get('node')
            if not node:
                continue
            if node.get('author'):  # PRs
                author_or_assignees = node['author']['login']
            else:  # Issues
                author_or_assignees = ', '.join(
                    a['node']['login'] for a in node['assignees']['edges']
                )

            labels = [
                lbl['name'].replace('|', '\\|')
                for lbl in node['labels']['nodes']
            ]
            rows.append(
                {
                    'id': node['id'],
                    'org_repo': node['repository']['nameWithOwner'],
                    'repo_name': node['repository']['name'],
                    'number': node['number'],
                    'title': node['title'].replace('|', '\\|'),
                    'author_or_assignees': author_or_assignees,
                    'created_at': node['createdAt'],
                    'closed_at': node['closedAt'],
                    'merged_at': node.get('mergedAt'),
                    'updated_at': node['updatedAt'],
                    'last_edit_at': node['lastEditedAt'],
                    'labels_raw': ', '.join(labels),
                    'labels': ', '.join(labels),
                    'state': node['state'],
                    'url': node['url'],
                }
            )
        columns = [
            'id',
            'org_repo',
            'repo_name',
            'type',
            'number',
            'title',
            'author_or_assignees',
            'created_at',
            'closed_at',
            'merged_at',
            'updated_at',
            'last_edit_at',
            'labels',
            'labels_raw',
            'state',
            'url',
        ]
        return pd.DataFrame(rows, columns=columns)


@public
class GHReportReader:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def get_data(self) -> pd.DataFrame:
        args: ArgsCLI = self.config.args
        if not self.config.gh_token:
            raise RuntimeError('Invalid GitHub token')
        if not args.start_date or not args.end_date:
            raise ValueError('start_date and end_date are required')
        if not self.config.repos:
            raise ValueError('At least one repository must be specified')
        if not self.config.authors:
            raise ValueError('At least one author must be specified')

        base = {
            'org_repos': self.config.repos,
            'authors': [next(iter(a), '') for a in self.config.authors],
            'start_date': args.start_date,
            'end_date': args.end_date,
        }
        searcher = _GitHubSearch(self.config.gh_token)
        dfs: list[pd.DataFrame] = []

        dfs.append(
            await searcher.search(
                GitHubSearchFilters(
                    **base,  # type: ignore[arg-type]
                    search_type='pr',
                    status=['OPEN'],
                    custom_filter={
                        'created': f'<={args.end_date}',
                        'updated': f'>={args.start_date}',
                    },
                )
            )
        )
        dfs.append(
            await searcher.search(
                GitHubSearchFilters(
                    **base,  # type: ignore[arg-type]
                    search_type='pr',
                    status=['MERGED'],
                    merged_at=True,
                )
            )
        )
        closed_prs = await searcher.search(
            GitHubSearchFilters(
                **base,  # type: ignore[arg-type]
                search_type='pr',
                status=['CLOSED'],
                closed_at=True,
            )
        )
        dfs.append(closed_prs[closed_prs.labels_raw.str.contains('Merged')])

        dfs.append(
            await searcher.search(
                GitHubSearchFilters(
                    **base,  # type: ignore[arg-type]
                    search_type='issue',
                    status=['CLOSED'],
                    closed_at=True,
                )
            )
        )

        return pd.concat(dfs, ignore_index=True)
