from __future__ import annotations

import asyncio
import io
import os

from pathlib import Path
from typing import cast

import dotenv
import yaml

from ghreport.config import ArgsCLI, Config
from ghreport.generator import GHReportGenerator
from ghreport.reader import GHReportReader

__all__ = ['GHReport']


class GHReport:
    """CLI entry-point coordinating data retrieval and report generation."""

    def __init__(self, args: ArgsCLI) -> None:
        self.args = args
        self.config_path = Path(args.config_file or '.ghreport.yaml').resolve()
        self.config = self._read_config()
        self.config.gh_token = self._resolve_token()

        self.reader = GHReportReader(self.config)
        self.generator = GHReportGenerator(self.config)

    def _read_config(self) -> Config:
        raw = self.config_path.read_text()
        cfg_dict = yaml.safe_load(io.StringIO(raw))
        cfg_dict['args'] = self.args
        cfg_dict['gh_token'] = ''
        normalised = {k.replace('-', '_'): v for k, v in cfg_dict.items()}
        return Config(**normalised)

    def _resolve_token(self) -> str:
        token = self.args.gh_token
        if token:
            return token

        env_file = self.config.env_file
        if env_file:
            env_path = Path(env_file)
            if not env_path.is_absolute():
                env_path = self.config_path.parent / env_path
            if not env_path.exists():
                raise FileNotFoundError(f'[EE] env-file not found: {env_path}')
            token = cast(
                str, dotenv.dotenv_values(env_path).get('GITHUB_TOKEN', '')
            )
        else:
            token = os.getenv('GITHUB_TOKEN', '')

        if not token:
            raise EnvironmentError(
                '`GITHUB_TOKEN` not provided via CLI, env-file, or environment'
                ' variable'
            )
        return token

    def run(self) -> None:
        asyncio.run(self.run_async())

    async def run_async(self) -> None:
        data = await self.reader.get_data()
        self.generator.generate(data)
