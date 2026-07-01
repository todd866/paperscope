"""Configuration loader for paper harvesting."""

from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel


class PathsConfig(BaseModel):
    output_dir: str = "~/Papers/harvester"

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser()


class DiscoveryConfig(BaseModel):
    interval_hours: int = 12
    max_papers_per_run: int = 30
    lookback_days: int = 7


class LibraryConfig(BaseModel):
    ezproxy_host: str = "ezproxy.library.usyd.edu.au"
    browser: str = "chrome"


class ResearchProfile(BaseModel):
    keywords: List[str] = []
    authors: List[str] = []
    arxiv_categories: List[str] = []
    semantic_scholar_fields: List[str] = []


class Config(BaseModel):
    paths: PathsConfig = PathsConfig()
    discovery: DiscoveryConfig = DiscoveryConfig()
    library: LibraryConfig = LibraryConfig()
    research_profile: ResearchProfile = ResearchProfile()

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load config from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def ensure_directories(self) -> None:
        """Create output directories if they don't exist."""
        output = self.paths.output_path
        (output / "inbox").mkdir(parents=True, exist_ok=True)
        (output / "keep").mkdir(parents=True, exist_ok=True)
        (output / "archive").mkdir(parents=True, exist_ok=True)
