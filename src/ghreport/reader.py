"""
Reader class reads data from GitHub using GraphQL.

Note: **dict approach is not working properly with mypy for dataclass:
  https://github.com/python/mypy/issues/5382
"""

from __future__ import annotations

import dataclasses
import re

from pathlib import Path
from typing import Any, Dict, List, Union

import pandas as pd

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from jinja2 import Template
from public import public

from ghreport.config import ArgsCLI, Config


class GitHubGraphQL:
    token: str
    transport: AIOHTTPTransport

    def __init__(self, token):
        self.token = token
        self.transport = AIOHTTPTransport(
            headers={'Authorization': f'bearer {self.token}'},
            url='https://api.github.com/graphql',
        )


@dataclasses.dataclass
class GitHubSearchFilters:
    org_repos: List[str] = dataclasses.field(default_factory=list)
    authors: List[str] = dataclasses.field(default_factory=list)
    search_type: str = 'pr'  # pr or issue
    start_date: str = ''
    end_date: str = ''
    status: List[str] = dataclasses.field(
        default_factory=list
    )  # open, closed, merged
    # uses start_date and end_date for merged_at filter
    merged_at: bool = False
    # uses start_date and end_date for closed_at filter
    closed_at: bool = False
    # uses start_date and end_date for updated_at filter
    updated_at: bool = False
    custom_filter: Dict[str, str] = dataclasses.field(default_factory=dict)


class GitHubSearch:
    ghgql: GitHubGraphQL
    template_file: Path

    def __init__(self, token: str) -> None:
        self.ghgql = GitHubGraphQL(token)
        self.template_file = (
            Path(__file__).parent / 'templates' / 'search.graphql'
        )

    def render_selector_template(
        self, template: str, input_data: Dict[str, str]
    ):
        re_selector = re.compile(
            """\#\s+\[(["']*\w+["']*)(==)(["']*\w+["']*)\s*\]*"""
        )

        result = template
        new_result = []

        for k, v in input_data.items():
            locals()[k] = v

        for line in result.split('\n'):
            if '#' not in line:
                new_result.append(line)
                continue

            re_result = re_selector.findall(line)

            if not re_result:
                new_result.append(line)
                continue

            re_result = re_result[0]
            re_validation = eval(''.join(re_result))

            if not re_validation:
                continue
            new_result.append(line[: line.find('#')])

        result = '\n'.join(new_result)

        return result

    async def pagination(self, variables: Dict[str, str]) -> pd.DataFrame:
        has_next_page = True
        pagination_after = ''
        limit = 100
        results = []
        has_result = False

        with open(self.template_file, 'r') as f:
            gql_tmpl = f.read()

        gql_tmpl = self.render_selector_template(gql_tmpl, variables)
        tmpl = Template(gql_tmpl)

        async with Client(
            transport=self.ghgql.transport,
            fetch_schema_from_transport=True,
        ) as session:
            while has_next_page:
                _variables = dict(variables)
                _variables.update(
                    after=''
                    if not pagination_after
                    else f', after: "{pagination_after}"'
                )

                gql_stmt = tmpl.render(**_variables)

                query = gql(gql_stmt)
                params = {'first': limit}

                result = await session.execute(query, variable_values=params)

                try:
                    page_info = result['search']['pageInfo']
                    has_next_page = page_info['hasNextPage']
                    pagination_after = page_info['endCursor']
                    has_result = True
                except IndexError:
                    has_next_page = False
                    has_result = False

                if not has_result:
                    break

            results += result['search']['edges']

        return self.to_dataframe(results)

    async def search(
        self, search_filters: GitHubSearchFilters
    ) -> pd.DataFrame:
        # Using `async with` on the client will start a connection on the
        # transport and provide a `session` variable to execute queries on
        # this connection

        if search_filters.search_type not in ['pr', 'issue']:
            raise Exception("search_type should be 'pr' or 'issue'")

        gql_node_type = (
            'PullRequest' if search_filters.search_type == 'pr' else 'Issue'
        )

        start_end_period = ''

        if search_filters.start_date and search_filters.end_date:
            start_end_period = '{{0}}:{0}..{1}'.format(
                search_filters.start_date, search_filters.end_date
            )

        variables = {
            'org_repos': ' '.join(
                [f'repo:{status}' for status in search_filters.org_repos]
            ),
            'gql_node_type': gql_node_type,
            'search_type': search_filters.search_type,
            'status': ' '.join(
                [f'is:{status}' for status in search_filters.status]
            ),
            'merged': (
                ''
                if not search_filters.merged_at
                else start_end_period.format('merged')
            ),
            'closed': (
                ''
                if not search_filters.closed_at
                else start_end_period.format('closed')
            ),
            'updated': (
                ''
                if not search_filters.updated_at
                else start_end_period.format('updated')
            ),
            'custom_filter': ' '.join(
                [f'{k}:{v}' for k, v in search_filters.custom_filter.items()]
            ),
        }

        if search_filters.authors:
            if search_filters.search_type == 'pr':
                variables['author'] = ' '.join(
                    f'author:{author}' for author in search_filters.authors
                )
            else:
                variables['assignee'] = ' '.join(
                    f'assignee:{assignee}'
                    for assignee in search_filters.authors
                )

        result = await self.pagination(variables)
        result['type'] = search_filters.search_type

        return result

    def to_dataframe(self, results: List[Dict[str, Any]]):
        data = []
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

        for node in results:
            n = node['node']

            if not n:
                continue

            author_or_assignees = (
                n['author']['login']
                if 'author' in n
                else ', '.join(
                    [edge['node']['login'] for edge in n['assignees']['edges']]
                )
            )

            _labels = [
                label['name'].replace('|', '\|')
                for label in n['labels']['nodes']
            ]

            content = {
                'id': n['id'],
                'org_repo': n['repository']['nameWithOwner'],
                'repo_name': n['repository']['name'],
                'number': n['number'],
                # "url": n["url"],
                'title': n['title'].replace('|', '\|'),
                'author_or_assignees': author_or_assignees,
                'created_at': n['createdAt'],
                'closed_at': n['closedAt'],
                'merged_at': n['mergedAt']
                if 'mergedAt' in n
                else None,  # not available for issues
                'updated_at': n['updatedAt'],
                'last_edit_at': n['lastEditedAt'],
                'labels_raw': ', '.join(_labels),
                'state': n['state'],
                'url': n['url'],
            }

            content['labels'] = content['labels_raw']

            data.append(content)

        return pd.DataFrame(data, columns=columns)


@public
class GHReportReader:
    """GHReportReader."""

    config: Config

    def __init__(self, config: Config) -> None:
        self.config: Config = config

    async def get_data(self) -> pd.DataFrame:
        """
        Return all the data used for the report.

        It contain:
          - open issues updated in a given date period.
          - open PRs with last edit or update in a given date period.
          - closed issues in a given date period.
          - closed issues in a given date period with label Merged
          - merged issues in a given date period.
        """
        args: ArgsCLI = self.config.args

        results = []

        gh_token = self.config.gh_token
        if not gh_token:
            raise Exception('Invalid GitHub token.')

        start_date = args.start_date
        if not start_date:
            raise Exception('`start_date` was not given.')

        end_date = args.end_date
        if not end_date:
            raise Exception('`end_date` was not given.')

        repos: List[str] = self.config.repos
        if not repos:
            raise Exception('No repository was given.')

        authors: List[Dict[str, str]] = self.config.authors
        if not authors:
            raise Exception('No authors was given.')

        general_params: Dict[
            str, Union[str, List[str], List[Dict[str, str]]]
        ] = dict(
            org_repos=repos,
            authors=[next(iter(author), '') for author in authors],
            start_date=start_date,
            end_date=end_date,
        )

        gh_searcher = GitHubSearch(gh_token)

        # open PRs with last update in a given date period.

        search_filters = GitHubSearchFilters(
            search_type='pr',
            status=['OPEN'],
            custom_filter={
                'created': f'<={end_date}',
                'updated': f'>={start_date}',
            },
            **general_params,  # type: ignore
        )
        results.append(await gh_searcher.search(search_filters))

        # merged prs in a given date period.
        search_filters = GitHubSearchFilters(
            search_type='pr',
            status=['MERGED'],
            merged_at=True,
            **general_params,  # type: ignore
        )
        results.append(await gh_searcher.search(search_filters))

        # closed prs in a given date period with label Merged

        search_filters = GitHubSearchFilters(
            search_type='pr',
            status=['CLOSED'],
            closed_at=True,
            **general_params,  # type: ignore
        )
        result = await gh_searcher.search(search_filters)
        result = result[result.labels_raw.apply(lambda v: 'Merged' in v)]
        results.append(result)

        # closed issues in a given date period.

        search_filters = GitHubSearchFilters(
            search_type='issue',
            status=['CLOSED'],
            closed_at=True,
            **general_params,  # type: ignore
        )
        results.append(await gh_searcher.search(search_filters))

        return pd.concat(results).reset_index(drop=True)
