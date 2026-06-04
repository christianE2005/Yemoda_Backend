import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi import status


def _make_signature(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()


PUSH_PAYLOAD = {
    "ref": "refs/heads/main",
    "before": "abc1234",
    "after": "def5678",
    "repository": {"full_name": "org/repo"},
    "pusher": {"name": "dev"},
    "commits": [],
    "installation": {"id": 99},
}


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == {"status": "ok"}


class TestWebhookSignature:
    def test_invalid_signature_returns_401(self, client):
        payload = json.dumps(PUSH_PAYLOAD).encode()
        with patch("app.routers.webhook._WEBHOOK_SECRET", "mysecret"):
            resp = client.post(
                "/webhook/push/",
                content=payload,
                headers={
                    "x-hub-signature-256": "sha256=invalidsignature",
                    "x-github-event": "push",
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_signature_with_secret_returns_401(self, client):
        payload = json.dumps(PUSH_PAYLOAD).encode()
        with patch("app.routers.webhook._WEBHOOK_SECRET", "mysecret"):
            resp = client.post(
                "/webhook/push/",
                content=payload,
                headers={
                    "x-hub-signature-256": "",
                    "x-github-event": "push",
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_valid_signature_accepted(self, client):
        payload = json.dumps(PUSH_PAYLOAD).encode()
        secret = "mysecret"
        sig = _make_signature(payload, secret)
        with patch("app.routers.webhook._WEBHOOK_SECRET", secret):
            with patch("app.routers.webhook._process_push"):
                resp = client.post(
                    "/webhook/push/",
                    content=payload,
                    headers={
                        "x-hub-signature-256": sig,
                        "x-github-event": "push",
                        "content-type": "application/json",
                    },
                )
        assert resp.status_code == status.HTTP_200_OK

    def test_no_secret_configured_rejects_requests(self, client):
        # Fail closed: with no configured secret the webhook must reject (not accept) requests.
        payload = json.dumps(PUSH_PAYLOAD).encode()
        with patch("app.routers.webhook._WEBHOOK_SECRET", ""):
            resp = client.post(
                "/webhook/push/",
                content=payload,
                headers={
                    "x-hub-signature-256": "",
                    "x-github-event": "push",
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestWebhookEventType:
    def test_non_push_event_is_ignored(self, client):
        secret = "testsecret"
        payload = json.dumps({}).encode()
        sig = _make_signature(payload, secret)
        with patch("app.routers.webhook._WEBHOOK_SECRET", secret):
            resp = client.post(
                "/webhook/push/",
                content=payload,
                headers={
                    "x-hub-signature-256": sig,
                    "x-github-event": "ping",
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == status.HTTP_200_OK
        assert "ignorado" in resp.json()["detail"]

    def test_push_event_dispatches_background_task(self, client):
        secret = "testsecret"
        payload = json.dumps(PUSH_PAYLOAD).encode()
        sig = _make_signature(payload, secret)
        with patch("app.routers.webhook._WEBHOOK_SECRET", secret):
            with patch("app.routers.webhook._process_push") as mock_task:
                resp = client.post(
                    "/webhook/push/",
                    content=payload,
                    headers={
                        "x-hub-signature-256": sig,
                        "x-github-event": "push",
                        "content-type": "application/json",
                    },
                )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["repository"] == "org/repo"
        assert data["ref"] == "refs/heads/main"
        mock_task.assert_called_once()


class TestWebhookPayload:
    def test_invalid_json_returns_400(self, client):
        secret = "testsecret"
        body = b"not-valid-json"
        sig = _make_signature(body, secret)
        with patch("app.routers.webhook._WEBHOOK_SECRET", secret):
            resp = client.post(
                "/webhook/push/",
                content=body,
                headers={
                    "x-hub-signature-256": sig,
                    "x-github-event": "push",
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_response_contains_repo_and_ref(self, client):
        secret = "testsecret"
        payload = json.dumps(PUSH_PAYLOAD).encode()
        sig = _make_signature(payload, secret)
        with patch("app.routers.webhook._WEBHOOK_SECRET", secret):
            with patch("app.routers.webhook._process_push"):
                resp = client.post(
                    "/webhook/push/",
                    content=payload,
                    headers={
                        "x-hub-signature-256": sig,
                        "x-github-event": "push",
                        "content-type": "application/json",
                    },
                )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "detail" in data
        assert data["repository"] == "org/repo"
        assert data["ref"] == "refs/heads/main"
