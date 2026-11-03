import toml  # type: ignore[import-untyped]
from adaptix import Retort

from timetabler.infrastructure.config.models import Config

_retort = Retort()


def load_config(config_path: str) -> Config:
    return _retort.load(toml.load(config_path), Config)
