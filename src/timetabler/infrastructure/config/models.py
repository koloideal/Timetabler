from dataclasses import dataclass


@dataclass
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class BotConfig:
    token: str
    creator_id: int


@dataclass
class SheetsConfig:
    credentials_path: str
    schedule_range: str = "A1:H50"
    date_cell: str = "A1"
    poll_interval_seconds: int = 180


@dataclass
class Config:
    postgres: PostgresConfig
    bot: BotConfig
    sheets: SheetsConfig
