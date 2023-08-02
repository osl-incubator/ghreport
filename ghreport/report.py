import asyncio
import io
import json
import os

from pathlib import Path
from typing import Dict, List, Union, cast

import dotenv
import pandas as pd
import yaml

from dotenv import load_dotenv
from jinja2 import Template

from ghreport.reader import GHReportReader
from ghreport.generator import GHReportGenerator
from ghreport.config import ArgsCLI, Config


class GHReport:
    reader: GHReportReader
    generator: GHReportGenerator
    config: Config
    args: ArgsCLI

    def __init__(self, args: ArgsCLI) -> None:
        config_file_default = str(Path(os.getcwd()) / ".ghreport.yaml")

        self.args: ArgsCLI = args
        self.config_file = args.config_file or config_file_default
        self.config: Config = self._read_config()

        self._load_token()

        self.reader = GHReportReader(self.config)
        self.generator = GHReportGenerator(self.config)

    def _read_config(self) -> Config:
        with open(self.config_file, "r") as f:
            # escape template tags
            content = f.read()
            f = io.StringIO(content)
            config_data = yaml.safe_load(f)

        config_data["args"] = self.args
        config_data["gh_token"] = ""
        return Config(
            **{k.replace("-", "_"): v for k, v in config_data.items()}
        )

    def _load_token(self) -> None:
        gh_token = self.args.gh_token
        if gh_token:
            self.config.gh_token = gh_token
            return

        env_file = self.config.env_file

        if not env_file:
            gh_token = os.getenv("GITHUB_TOKEN", "")

            if gh_token:
                raise Exception(
                    "`GITHUB_TOKEN` environment variable not found"
                )

            self.config.gh_token = gh_token
            return

        if not env_file.startswith("/"):
            # use makim file as reference for the working directory
            # for the .env file
            env_file = str(Path(self.config_file).parent / env_file)

        if not Path(env_file).exists():
            raise Exception(
                f"[EE] The given env-file ({env_file}) was not found."
            )

        envs = dotenv.dotenv_values(env_file)
        gh_token = cast(str, envs.get("GITHUB_TOKEN", ""))

        if not gh_token:
            raise Exception("`GITHUB_TOKEN` environment variable not found")

        self.config.gh_token = gh_token

    def run(self) -> None:
        asyncio.run(self.run_async())

    async def run_async(self):
        data = await self.reader.get_data()
        self.generator.generate(data)
