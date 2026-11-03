import toml  # type: ignore[import-untyped]
from adaptix import Retort

from timetabler.infrastructure.config.models import Config


def load_config(config_path: str) -> Config:
    return Retort().load(toml.load(config_path), Config)
