import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from timetabler.application.ports import CreatorNotifier, MassSender
from timetabler.application.ports.mass_sender import COPY_BLOCKED, COPY_OK
from timetabler.application.services.audience import Audience
from timetabler.infrastructure.config.app import MassBroadcastConfig


@dataclass
class BroadcastJob:
    id: int
    label: str
    from_chat_id: int
    message_id: int
    users: list[int]
    chats: list[int]
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    cancelled: bool = False
    task: asyncio.Task | None = None

    @property
    def total(self) -> int:
        return len(self.users) + len(self.chats)

    @property
    def done(self) -> int:
        return self.sent + self.blocked + self.failed

    @property
    def running(self) -> bool:
        return self.finished_at is None


class MassBroadcastService:
    def __init__(
        self, sender: MassSender, notifier: CreatorNotifier, config: MassBroadcastConfig
    ) -> None:
        self.sender = sender
        self.notifier = notifier
        self.config = config
        self._jobs: dict[int, BroadcastJob] = {}
        self._counter = 0
        self._logger = logging.getLogger(__name__)
        self._events = logging.getLogger("events")

    def active(self) -> BroadcastJob | None:
        return next((j for j in self._jobs.values() if j.running), None)

    def latest(self) -> BroadcastJob | None:
        return self._jobs[max(self._jobs)] if self._jobs else None

    def get(self, job_id: int) -> BroadcastJob | None:
        return self._jobs.get(job_id)

    def start(
        self, audience: Audience, from_chat_id: int, message_id: int, label: str
    ) -> BroadcastJob:
        if self.active() is not None:
            raise RuntimeError("Another broadcast is already running")
        self._counter += 1
        job = BroadcastJob(
            id=self._counter,
            label=label,
            from_chat_id=from_chat_id,
            message_id=message_id,
            users=list(dict.fromkeys(audience.user_ids)),
            chats=list(dict.fromkeys(audience.chat_ids)),
        )
        self._jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job))
        return job

    def cancel(self, job_id: int) -> bool:
        job = self._jobs.get(job_id)
        if job is None or not job.running:
            return False
        job.cancelled = True
        return True

    async def _run(self, job: BroadcastJob) -> None:
        self._events.info(
            "📣 Рассылка #%s запущена: %s — юзеров %s, чатов %s",
            job.id, job.label, len(job.users), len(job.chats),
        )
        try:
            for chat_id in [*job.users, *job.chats]:
                if job.cancelled:
                    break
                result = await self.sender.copy_to(
                    chat_id, job.from_chat_id, job.message_id
                )
                if result == COPY_OK:
                    job.sent += 1
                elif result == COPY_BLOCKED:
                    job.blocked += 1
                else:
                    job.failed += 1
                await asyncio.sleep(self.config.send_interval_seconds)
        except Exception:
            self._logger.exception("Mass broadcast #%s crashed", job.id)
        finally:
            job.finished_at = datetime.now(timezone.utc)
        await self._report(job)

    async def _report(self, job: BroadcastJob) -> None:
        finished = job.finished_at or datetime.now(timezone.utc)
        seconds = (finished - job.started_at).total_seconds()
        skipped = job.total - job.done
        head = "⛔ Рассылка остановлена" if job.cancelled else "📣 Рассылка завершена"
        self._events.info(
            "%s #%s: отправлено %s, заблокировали бота %s, ошибок %s, не дошла очередь %s за %.0f с",
            head, job.id, job.sent, job.blocked, job.failed, skipped, seconds,
        )
        lines = [
            f"<b>{head}</b> · #{job.id}",
            f"<b>Аудитория:</b> {job.label}",
            f"✅ Доставлено: {job.sent} из {job.total}",
        ]
        if job.blocked:
            lines.append(f"🚫 Заблокировали бота / нет доступа: {job.blocked}")
        if job.failed:
            lines.append(f"❌ Ошибки: {job.failed}")
        if skipped:
            lines.append(f"⏭ Не отправлено (остановлена): {skipped}")
        lines.append(f"⏱ Время: {seconds:.0f} с")
        try:
            await self.notifier.notify_creator("\n".join(lines))
        except Exception:
            self._logger.exception("Cannot send mass broadcast report")
