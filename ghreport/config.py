from dataclasses import dataclass, field
from typing import Dict, List

from public import public


@dataclass
class ArgsCLI:
    start_date: str = ""
    end_date: str = ""
    gh_token: str = ""
    config_file: str = ""


@dataclass
class Config:
    name: str = ""
    title: str = ""
    env_file: str = ""
    repos: List[str] = field(default_factory=list)
    authors: List[Dict[str, str]] = field(default_factory=list)
    output_dir: str = ""
    args: ArgsCLI = field(default_factory=ArgsCLI)
    gh_token: str = ""
