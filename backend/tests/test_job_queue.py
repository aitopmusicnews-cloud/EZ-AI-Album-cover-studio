from __future__ import annotations

import json

import pytest

from app.job_queue import GenerationJob, SQSGenerationQueue


class FakeSQSClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []
        self.changed: list[dict] = []
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "message-1"}

    def receive_message(self, **kwargs):
        return {"Messages": list(self.messages)}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def change_message_visibility(self, **kwargs):
        self.changed.append(kwargs)


def test_generation_job_round_trip() -> None:
    original = GenerationJob(
        action="process",
        generation_id="generation-1",
        variation_count=4,
        mood_path="blend",
    )

    restored = GenerationJob.from_body(original.to_body())

    assert restored == original


def test_generation_job_rejects_invalid_action() -> None:
    with pytest.raises(ValueError, match="Unsupported generation job action"):
        GenerationJob(action="unknown", generation_id="generation-1")


def test_queue_enqueues_compact_json_message() -> None:
    client = FakeSQSClient()
    queue = SQSGenerationQueue(
        queue_url="https://sqs.us-west-2.amazonaws.com/123/jobs",
        region_name="us-west-2",
        client=client,
    )

    message_id = queue.enqueue(
        action="improve",
        generation_id="generation-1",
        variation_count=3,
        mood_path="lyrics",
    )

    assert message_id == "message-1"
    body = json.loads(client.sent[0]["MessageBody"])
    assert body == {
        "action": "improve",
        "generation_id": "generation-1",
        "mood_path": "lyrics",
        "variation_count": 3,
    }


def test_queue_receives_deletes_and_extends_visibility() -> None:
    client = FakeSQSClient()
    client.messages = [{"MessageId": "message-1", "ReceiptHandle": "receipt", "Body": "{}"}]
    queue = SQSGenerationQueue(
        queue_url="https://sqs.us-west-2.amazonaws.com/123/jobs",
        visibility_timeout_seconds=900,
        client=client,
    )

    assert queue.receive() == client.messages
    queue.extend_visibility("receipt")
    queue.delete("receipt")

    assert client.changed[0]["VisibilityTimeout"] == 900
    assert client.deleted[0]["ReceiptHandle"] == "receipt"


def test_disabled_queue_has_no_aws_client() -> None:
    queue = SQSGenerationQueue(queue_url=None)

    assert queue.enabled is False
    with pytest.raises(RuntimeError, match="not configured"):
        queue.enqueue(action="process", generation_id="generation-1")
