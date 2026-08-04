from __future__ import annotations

import asyncio
import logging
import signal
import threading
from types import FrameType

from .job_queue import GenerationJob
from .main import app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ez_ai_worker")

_COMPLETED_STATUSES = {"complete", "partial", "needs_mood_choice"}
_INCOMPLETE_SET_STATUSES = {"failed", "partial", "generating", "rendering"}


async def dispatch_job(service, job: GenerationJob) -> None:
    if job.action == "process":
        with service.database.session_factory() as db:
            generation = service.get(db, job.generation_id)
            status = generation.status
            has_incomplete_set = any(
                item.status in _INCOMPLETE_SET_STATUSES
                for item in generation.variation_sets
            )

        if status in _COMPLETED_STATUSES:
            logger.info(
                "Skipping completed generation %s with status %s",
                job.generation_id,
                status,
            )
            return

        if status in {"generating", "image_failed", "analysis_failed"} or has_incomplete_set:
            await service.retry_failed(job.generation_id)
            return

        await service.process_generation(
            job.generation_id,
            job.variation_count,
            job.mood_path,
        )
        return

    if job.action == "regenerate":
        await service.regenerate(
            job.generation_id,
            job.variation_count,
            job.mood_path,
        )
        return

    if job.action == "improve":
        improve = getattr(service, "generate_better", None)
        if improve is None:
            raise RuntimeError("Generate Better is not enabled")
        await improve(
            job.generation_id,
            job.variation_count,
            job.mood_path,
        )
        return

    if job.action == "retry":
        await service.retry_failed(job.generation_id)
        return

    raise ValueError(f"Unsupported generation job action: {job.action}")


def visibility_heartbeat(queue, receipt_handle: str, stop_event: threading.Event, seconds: int) -> None:
    while not stop_event.wait(seconds):
        try:
            queue.extend_visibility(receipt_handle)
            logger.info("Extended SQS visibility timeout")
        except Exception:
            logger.exception("Unable to extend SQS visibility timeout")


def run() -> None:
    settings = app.state.settings
    database = app.state.database
    service = app.state.generation_service
    queue = app.state.job_queue

    if not queue.enabled:
        raise RuntimeError("SQS_QUEUE_URL is required for the worker")

    database.create_all()
    shutdown = threading.Event()

    def stop_handler(_: int, __: FrameType | None) -> None:
        logger.info("Worker shutdown requested")
        shutdown.set()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    logger.info("Generation worker started")

    while not shutdown.is_set():
        try:
            messages = queue.receive(max_messages=1, wait_seconds=20)
        except Exception:
            logger.exception("Unable to receive SQS messages")
            shutdown.wait(5)
            continue

        for message in messages:
            receipt_handle = str(message["ReceiptHandle"])
            message_id = str(message.get("MessageId", "unknown"))
            try:
                job = GenerationJob.from_body(str(message["Body"]))
            except Exception:
                logger.exception("Invalid SQS message %s; leaving it for the dead-letter queue", message_id)
                continue

            logger.info(
                "Processing SQS message %s: %s %s",
                message_id,
                job.action,
                job.generation_id,
            )

            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=visibility_heartbeat,
                args=(
                    queue,
                    receipt_handle,
                    heartbeat_stop,
                    settings.sqs_visibility_heartbeat_seconds,
                ),
                daemon=True,
            )
            heartbeat.start()

            try:
                asyncio.run(dispatch_job(service, job))
                queue.delete(receipt_handle)
                logger.info("Completed SQS message %s", message_id)
            except Exception:
                logger.exception(
                    "Generation job failed; SQS will retry message %s",
                    message_id,
                )
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=2)

    logger.info("Generation worker stopped")


if __name__ == "__main__":
    run()
