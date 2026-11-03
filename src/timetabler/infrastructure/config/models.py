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
class GoogleConfig:
    credentials_path: str


@dataclass
class Config:
    postgres: PostgresConfig
    bot: BotConfig
    google: GoogleConfig
