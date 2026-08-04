from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

import boto3


_ALLOWED_ACTIONS = {"process", "regenerate", "improve", "retry"}
_ALLOWED_MOOD_PATHS = {"auto", "blend", "audio", "lyrics"}


@dataclass(frozen=True, slots=True)
class GenerationJob:
    action: str
    generation_id: str
    variation_count: int = 4
    mood_path: str = "auto"

    def __post_init__(self) -> None:
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported generation job action: {self.action}")
        if not self.generation_id.strip():
            raise ValueError("generation_id is required")
        if not 3 <= self.variation_count <= 8:
            raise ValueError("variation_count must be between 3 and 8")
        if self.mood_path not in _ALLOWED_MOOD_PATHS:
            raise ValueError(f"Unsupported mood path: {self.mood_path}")

    def to_body(self) -> str:
        return json.dumps(
            {
                "action": self.action,
                "generation_id": self.generation_id,
                "variation_count": self.variation_count,
                "mood_path": self.mood_path,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_body(cls, body: str) -> "GenerationJob":
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("SQS message body must be a JSON object")
        return cls(
            action=str(payload.get("action", "")),
            generation_id=str(payload.get("generation_id", "")),
            variation_count=int(payload.get("variation_count", 4)),
            mood_path=str(payload.get("mood_path", "auto")),
        )


@dataclass(slots=True)
class SQSGenerationQueue:
    queue_url: str | None
    region_name: str = "us-west-2"
    visibility_timeout_seconds: int = 900
    client: Any | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.queue_url = (self.queue_url or "").strip() or None
        if self.queue_url and self.client is None:
            self.client = boto3.client("sqs", region_name=self.region_name)

    @property
    def enabled(self) -> bool:
        return bool(self.queue_url and self.client)

    def enqueue(
        self,
        *,
        action: str,
        generation_id: str,
        variation_count: int = 4,
        mood_path: str = "auto",
    ) -> str:
        if not self.enabled:
            raise RuntimeError("SQS generation queue is not configured")
        job = GenerationJob(
            action=action,
            generation_id=generation_id,
            variation_count=variation_count,
            mood_path=mood_path,
        )
        response = self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=job.to_body(),
        )
        return str(response["MessageId"])

    def receive(self, *, max_messages: int = 1, wait_seconds: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            raise RuntimeError("SQS generation queue is not configured")
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max(1, min(max_messages, 10)),
            WaitTimeSeconds=max(0, min(wait_seconds, 20)),
            VisibilityTimeout=self.visibility_timeout_seconds,
            AttributeNames=["ApproximateReceiveCount"],
        )
        return list(response.get("Messages", []))

    def delete(self, receipt_handle: str) -> None:
        if not self.enabled:
            raise RuntimeError("SQS generation queue is not configured")
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )

    def extend_visibility(self, receipt_handle: str) -> None:
        if not self.enabled:
            raise RuntimeError("SQS generation queue is not configured")
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=self.visibility_timeout_seconds,
        )
