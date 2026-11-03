import asyncio
import logging
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error

logger = logging.getLogger(__name__)

SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)

MAX_ATTEMPTS = 4
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0


class SheetAccessError(Exception):
    pass


class GoogleSheetsClient:
    def __init__(self, credentials_path: str) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
        self.service_account_email: str = credentials.service_account_email
        self._values = build(
            "sheets", "v4", credentials=credentials, cache_discovery=False
        ).spreadsheets().values()

    async def read_values(self, spreadsheet_id: str, a1_range: str) -> list[list[Any]]:
        delay = RETRY_BASE_DELAY
        for attempt in range(MAX_ATTEMPTS):
            try:
                request = self._values.get(spreadsheetId=spreadsheet_id, range=a1_range)
                response = await asyncio.to_thread(request.execute)
                return response.get("values") or []
            except HttpError as e:
                if e.status_code == 404:
                    raise SheetAccessError("таблица не найдена — проверьте ID") from e
                if e.status_code == 403:
                    raise SheetAccessError("нет доступа — расшарьте таблицу на сервисный аккаунт") from e
                if e.status_code != 429 or attempt == MAX_ATTEMPTS - 1:
                    raise
            except (HttpLib2Error, ConnectionError, TimeoutError, OSError):
                if attempt == MAX_ATTEMPTS - 1:
                    raise
            logger.warning(
                "Sheets read %s attempt %s/%s failed, retrying in %.0fs",
                a1_range, attempt + 1, MAX_ATTEMPTS, delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_DELAY)
        raise AssertionError("unreachable")
