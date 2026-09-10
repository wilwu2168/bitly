"""Locust scenarios that expose concurrency limits in the Bitly clone."""

from __future__ import annotations

import logging
import random
import uuid

import requests
from locust import HttpUser, between, events, task

DEFAULT_HOST = "http://127.0.0.1:8000"
HOT_CODE = f"hot-{uuid.uuid4().hex[:10]}"
HOT_URL = "https://example.com/hot-link"

hot_redirect_attempts = 0
hot_redirect_successes = 0

logger = logging.getLogger(__name__)


def target_host(environment) -> str:
    return environment.host or DEFAULT_HOST


@events.test_start.add_listener
def seed_hot_link(environment, **_kwargs) -> None:
    """Create one shared link before users start stampeding it."""
    global hot_redirect_attempts, hot_redirect_successes

    hot_redirect_attempts = 0
    hot_redirect_successes = 0
    response = requests.post(
        f"{target_host(environment)}/links",
        json={"url": HOT_URL, "custom_code": HOT_CODE},
        timeout=10,
    )
    if response.status_code not in (201, 409):
        raise RuntimeError(
            f"Could not seed hot link: {response.status_code} {response.text}"
        )

    logger.info("Seeded hot link /%s for the redirect stampede", HOT_CODE)


@events.test_stop.add_listener
def audit_hot_link(environment, **_kwargs) -> None:
    """Compare successful redirect responses with the persisted click count."""
    try:
        response = requests.get(
            f"{target_host(environment)}/links/{HOT_CODE}",
            timeout=10,
        )
        response.raise_for_status()
        stored_clicks = response.json()["clicks"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.error(
            "CLICK AUDIT: attempts=%d successful_302s=%d "
            "stored_clicks=unavailable (API unreachable: %s)",
            hot_redirect_attempts,
            hot_redirect_successes,
            exc,
        )
        return

    difference = stored_clicks - hot_redirect_successes
    logger.warning(
        "CLICK AUDIT: attempts=%d successful_302s=%d stored_clicks=%d delta=%+d",
        hot_redirect_attempts,
        hot_redirect_successes,
        stored_clicks,
        difference,
    )


class RedirectStampede(HttpUser):
    """Hammer the same row with concurrent click increments."""

    host = DEFAULT_HOST
    weight = 5
    wait_time = between(0.01, 0.08)

    @task
    def redirect_hot_link(self) -> None:
        global hot_redirect_attempts, hot_redirect_successes

        hot_redirect_attempts += 1
        with self.client.get(
            f"/{HOT_CODE}",
            name="/{hot_code}",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code == 302:
                hot_redirect_successes += 1
                response.success()
            else:
                response.failure(
                    f"expected 302, got {response.status_code}: {response.text}"
                )


class CreateStorm(HttpUser):
    """Continuously create rows to produce SQLite write contention."""

    host = DEFAULT_HOST
    weight = 2
    wait_time = between(0.02, 0.15)

    @task
    def create_link(self) -> None:
        unique_id = uuid.uuid4().hex
        with self.client.post(
            "/links",
            json={"url": f"https://example.com/create/{unique_id}"},
            name="/links [create storm]",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(
                    f"expected 201, got {response.status_code}: {response.text}"
                )


class MixedUser(HttpUser):
    """Exercise normal create, redirect, stats, and update traffic."""

    host = DEFAULT_HOST
    weight = 3
    wait_time = between(0.05, 0.3)

    personal_code: str | None = None

    def on_start(self) -> None:
        response = self.client.post(
            "/links",
            json={"url": f"https://example.com/user/{uuid.uuid4().hex}"},
            name="/links [mixed setup]",
        )
        if response.status_code == 201:
            self.personal_code = response.json()["code"]

    @task(6)
    def redirect(self) -> None:
        if self.personal_code is not None:
            self.client.get(
                f"/{self.personal_code}",
                name="/{personal_code}",
                allow_redirects=False,
            )

    @task(3)
    def stats(self) -> None:
        if self.personal_code is not None:
            self.client.get(
                f"/links/{self.personal_code}",
                name="/links/{personal_code} [stats]",
            )

    @task(1)
    def update(self) -> None:
        if self.personal_code is not None:
            self.client.patch(
                f"/links/{self.personal_code}",
                json={
                    "url": (
                        "https://example.com/updated/"
                        f"{random.randint(1, 1_000_000)}"
                    )
                },
                name="/links/{personal_code} [update]",
            )
