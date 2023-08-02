import json
import os

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from dotenv import load_dotenv
from jinja2 import Template

from ghreport.reader import GHReportReader
from ghreport.config import Config


class GHReportGenerator:
    config: Config

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.project_path = str(Path(__file__).absolute().parent)
        self.date_cols = [
            "created_at",
            "closed_at",
            "merged_at",
            "updated_at",
            "last_edit_at",
        ]

    def _get_table_name_from_params(self, params: Dict[str, str]) -> str:
        if "title" in params:
            return params["title"]

        # repo is required
        fmt = "{} - {}" if "label" in params else "{}{}"
        return fmt.format(params.get("repo"), params.get("label", ""))

    def _get_template(self) -> Template:
        template_path = str(
            Path(self.project_path) / "templates" / "template.md"
        )

        with open(template_path) as f:
            return Template(f.read())

    def _get_output_columns(self) -> list:
        return [
            "repo_name",
            "number",
            "title",
            "author",
            "assignees",
            "labels",
            "state",
        ] + self.date_cols

    def _prepare_output_dataframe(self, results: pd.DataFrame) -> pd.DataFrame:
        # date truncate
        for col in self.date_cols:
            results[col] = results[col].apply(
                lambda v: v[:10] if isinstance(v, str) else None
            )

        # add link to number column
        results.number = results.apply(
            lambda series: (
                f"""<a href='{series["url"]}'>{series["number"]}</a>"""
            ),
            axis=1,
        )

        # combine merged and closed for prs
        results.loc[results.type == "pr", "merged_at"] = results[
            results.type == "pr"
        ].apply(
            lambda series: (
                series["merged_at"]
                if series["merged_at"]
                else series["closed_at"]
                if "Merged" in series["labels_raw"]
                else None
            ),
            axis=1,
        )
        results.loc[results.type == "pr", "state"] = results[
            results.type == "pr"
        ].apply(
            lambda series: (
                series["state"]
                if series["state"] != "CLOSED"
                else series["closed_at"]
                if "Merged" not in series["labels_raw"]
                else "MERGED"
            ),
            axis=1,
        )

        gh_users = {}
        for author in self.config.authors:
            gh_users.update(author)

        # Map real name for authors and assignees
        results.author_or_assignees = results.apply(
            lambda series: (
                series["author_or_assignees"]
                if series["author_or_assignees"] not in gh_users
                else gh_users[series["author_or_assignees"]]
            ),
            axis=1,
        )

        results["author"] = results.author_or_assignees
        results["assignees"] = results.author_or_assignees

        return results

    def _get_issues_cols(self, output_cols: list) -> list:
        # PR's columns
        prs_cols = [
            "created_at",
            "merged_at",
            "updated_at",
            "last_edit_at",
            "author",
        ]
        return [col for col in output_cols if col not in prs_cols]

    def _get_prs_cols(self, output_cols: list) -> list:
        # issue's columns
        issues_cols = [
            "closed_at",
            "created_at",
            "updated_at",
            "last_edit_at",
            "assignees",
        ]

        return [col for col in output_cols if col not in issues_cols]

    def get_output_filepath_from_args(self, extension: str) -> str:
        args = self.config.args
        start_date = args.start_date
        end_date = args.end_date

        filename = (
            f"report-{self.config.name}-"
            f"{start_date.replace('-', '')}-"
            f"{end_date.replace('-', '')}.{extension}"
        )
        return str(Path(self.config.output_dir) / filename)

    def _create_file(self, tmpl: Template, projects: List[Dict[str, str]]):
        args = self.config.args

        filepath = self.get_output_filepath_from_args(extension="md")
        dirpath = Path(filepath).parent

        os.makedirs(dirpath, exist_ok=True)

        report_title = self.config.title or "Report"
        repos = self.config.repos
        authors = self.config.authors
        start_date = args.start_date
        end_date = args.end_date

        authors_username = [next(iter(author), "") for author in authors]

        with open(filepath, "w") as f:
            content = tmpl.render(
                report_title=report_title,
                orgs_repos=", ".join(repos),
                authors=", ".join(authors_username),
                start_date=start_date,
                end_date=end_date,
                projects=projects,
            )
            f.write(content)

    def _get_output_tables_by_repos(
        self, results: pd.DataFrame
    ) -> List[Dict[str, str]]:
        # prepare output columns
        results_cols = self._get_output_columns()
        issues_cols = self._get_issues_cols(results_cols)
        prs_cols = self._get_prs_cols(results_cols)

        repos = self.config.repos

        projects: List[Dict[str, str]] = []

        for repo in repos:
            df = results[results.org_repo == repo]

            df_prs = df[df.type == "pr"][prs_cols].reset_index(drop=True)
            df_issues = df[df.type == "issue"][issues_cols].reset_index(
                drop=True
            )

            projects.append(
                {
                    "name": repo.split("/")[1],
                    "pr_results": (
                        df_prs.to_markdown(index=False)
                        if not df_prs.empty
                        else "None"
                    ),
                    "issue_results": (
                        df_issues.to_markdown(index=False)
                        if not df_issues.empty
                        else "None"
                    ),
                }
            )
        return projects

    def _get_output_tables(
        self, results: pd.DataFrame
    ) -> List[Dict[str, str]]:
        return self._get_output_tables_by_repos(results)

    def generate(self, results: pd.DataFrame) -> None:
        # get the markdown template
        tmpl = self._get_template()

        # prepare the dataframe according to the given parameters
        self._prepare_output_dataframe(results)

        # prepare data tables
        output_tables = self._get_output_tables(results)

        # create the markdown file
        self._create_file(tmpl, output_tables)
