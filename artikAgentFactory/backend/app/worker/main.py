"""Run-queue worker — the AWS execution path for scheduled/manual agent runs (see
approved plan §11/19). Long-polls SQS, and for each message calls the EXACT SAME
`execute_run()` used by local/manual runs — zero pipeline changes needed for AWS.

Entry point for the ECS `run-worker` service (see infra/stacks/compute_stack.py),
selected via `WORKER_ROLE=run` in the container environment. Not used when
`EXECUTION_BACKEND=inline` (local dev) — see scheduler/scheduler.py and
api/routers/agents.py for where that split happens.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time

from app.core.database import SessionLocal
from app.core.logging_config import log_event, setup_logging

_shutdown = False


def _handle_sigterm(signum, frame):  # noqa: ANN001
    global _shutdown
    _shutdown = True
    log_event("app", "run-worker received shutdown signal, finishing in-flight message then exiting")


def _process_message(sqs_client, queue_url: str, message: dict) -> None:
    from app.models.agent import Agent
    from app.services.run_service import execute_run

    receipt_handle = message["ReceiptHandle"]
    try:
        body = json.loads(message["Body"])
        agent_id = int(body["agent_id"])
        trigger = body.get("trigger", "scheduled")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        # Malformed message — delete it rather than let it retry forever; a bad
        # payload will never become valid on redelivery.
        log_event("error", "run-worker: malformed queue message, dropping", error=str(e))
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        return

    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        if agent is None or agent.status != "active":
            log_event("app", "run-worker: agent missing or inactive, skipping", agent_id=agent_id)
        else:
            run = execute_run(db, agent, trigger=trigger)
            log_event("app", "run-worker: run completed", agent_id=agent_id, run_id=run.id, status=run.status)
        # Delete on any outcome execute_run() itself handled gracefully (including
        # status="failed") — it never raises. Only an uncaught exception below
        # leaves the message for SQS's native redelivery/DLQ (maxReceiveCount=3).
        sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    finally:
        db.close()


def run_forever() -> None:
    import boto3

    setup_logging("INFO")
    signal.signal(signal.SIGTERM, _handle_sigterm)

    queue_url = os.environ.get("RUN_QUEUE_URL")
    if not queue_url:
        log_event("error", "run-worker: RUN_QUEUE_URL not set, exiting")
        sys.exit(1)

    sqs = boto3.client("sqs")
    log_event("app", "run-worker started", queue_url=queue_url)

    while not _shutdown:
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20,
                VisibilityTimeout=600,  # a run can take several minutes of real web-search calls
            )
            for message in resp.get("Messages", []):
                _process_message(sqs, queue_url, message)
        except Exception as e:  # noqa: BLE001 — the poll loop must never die
            log_event("error", "run-worker: poll loop error", error=str(e))
            time.sleep(5)

    log_event("app", "run-worker exiting cleanly")


if __name__ == "__main__":
    run_forever()
