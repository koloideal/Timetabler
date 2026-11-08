import asyncio
import logging

from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error

from timetabler.infrastructure.config.app import SheetsClientConfig


class SheetAccessError(Exception):
    pass


class GoogleSheetsClient:
    def __init__(self, config: SheetsClientConfig, credentials_path: str) -> None:
        self.config = config
        self.credentials_path = credentials_path
        self._values: Resource | None = None
        self._files: Resource | None = None
        self.service_account_email: str | None = None
        self._logger = logging.getLogger(__name__)

    def _ensure_configured(self) -> None:
        if self._values is not None:
            return
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.config.scopes
            )
            self._values = build(
                "sheets", "v4", credentials=credentials, cache_discovery=False
            ).spreadsheets().values()
            self._files = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            ).files()
        except FileNotFoundError as e:
            raise SheetAccessError(f"файл ключа не найден: {self.credentials_path}") from e
        except (ValueError, OSError, DefaultCredentialsError) as e:
            raise SheetAccessError(f"невалидный ключ сервисного аккаунта: {e}") from e
        except Exception as e:
            self._logger.exception(
                "Failed to configure Sheets client from %s", self.credentials_path
            )
            raise SheetAccessError(f"не удалось загрузить ключ сервисного аккаунта: {e}") from e
        self.service_account_email = credentials.service_account_email
        self._logger.info("Sheets client configured: %s", self.service_account_email)

    async def read_values(self, spreadsheet_id: str, a1_range: str) -> list[list[object]]:
        self._ensure_configured()

        delay = self.config.retry_base_delay
        for attempt in range(self.config.max_attempts):
            self._logger.info(
                "Sheets read: %s!%s (attempt %s/%s)",
                spreadsheet_id, a1_range, attempt + 1, self.config.max_attempts,
            )
            try:
                if self._values is not None:
                    request = self._values.get(
                        spreadsheetId=spreadsheet_id, range=a1_range
                    )
                else:
                    raise RuntimeError("Sheets values resource not initialised")
                response = await asyncio.to_thread(request.execute)
            except HttpError as e:
                if e.status_code == 404:
                    raise SheetAccessError("таблица не найдена — проверьте ID") from e
                if e.status_code == 403:
                    raise SheetAccessError("нет доступа — расшарьте таблицу на сервисный аккаунт") from e
                if e.status_code != 429:
                    self._logger.warning(
                        "Google API error %s on %s!%s: %s",
                        e.status_code, spreadsheet_id, a1_range, e,
                    )
                    raise SheetAccessError(f"ошибка Google API ({e.status_code})") from e
                if attempt == self.config.max_attempts - 1:
                    self._logger.warning(
                        "Google API rate limit on %s!%s after %s attempts",
                        spreadsheet_id, a1_range, self.config.max_attempts,
                    )
                    raise SheetAccessError("превышен лимит запросов Google API") from e
            except (HttpLib2Error, ConnectionError, TimeoutError, OSError) as e:
                if attempt == self.config.max_attempts - 1:
                    self._logger.exception(
                        "Sheets request %s!%s failed after %s attempts",
                        spreadsheet_id, a1_range, self.config.max_attempts,
                    )
                    raise SheetAccessError(f"сетевая ошибка: {e}") from e
            except Exception:
                self._logger.exception(
                    "Unexpected Sheets error on %s!%s", spreadsheet_id, a1_range
                )
                raise
            else:
                values: list[list[object]] = response.get("values") or []
                self._logger.info(
                    "Sheets read ok: %s!%s -> %s rows", spreadsheet_id, a1_range, len(values)
                )
                return values
            self._logger.warning(
                "Sheets read %s!%s attempt %s/%s failed, retrying in %.0fs",
                spreadsheet_id, a1_range, attempt + 1, self.config.max_attempts, delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, self.config.retry_max_delay)
        raise AssertionError("unreachable")

    async def export_xlsx(self, spreadsheet_id: str) -> bytes:
        self._ensure_configured()
        self._logger.info("Sheets export xlsx: %s", spreadsheet_id)
        try:
            if self._files is None:
                raise RuntimeError("Sheets files resource not initialised")
            request = self._files.export_media(
                fileId=spreadsheet_id,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            content: bytes = await asyncio.to_thread(request.execute)
            return content
        except HttpError as e:
            if e.status_code == 404:
                raise SheetAccessError("таблица не найдена — проверьте ID") from e
            if e.status_code == 403:
                raise SheetAccessError("нет доступа — расшарьте таблицу на сервисный аккаунт") from e
            raise
