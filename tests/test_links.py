"""The spec for the Bitly clone. Every test talks to your app purely
over HTTP — storage choices are invisible to this suite.

Run one stage at a time:
    pytest -m stage1
    pytest -m stage2
    ...
    pytest            (everything)
"""

import uuid

import pytest


def unique_url() -> str:
    return f"https://example.com/{uuid.uuid4().hex}"


def unique_code() -> str:
    return f"nope-{uuid.uuid4().hex[:10]}"


def create_link(client, **overrides):
    payload = {"url": unique_url()}
    payload.update(overrides)
    r = client.post("/links", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- stage 1


@pytest.mark.stage1
def test_create_returns_201_with_code_url_clicks(client):
    url = unique_url()
    r = client.post("/links", json={"url": url})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["url"] == url
    assert isinstance(body["code"], str) and 0 < len(body["code"]) <= 16
    assert body["clicks"] == 0


@pytest.mark.stage1
def test_same_url_twice_yields_distinct_codes(client):
    url = unique_url()
    r1 = client.post("/links", json={"url": url})
    r2 = client.post("/links", json={"url": url})
    assert r1.json()["code"] != r2.json()["code"]


@pytest.mark.stage1
def test_redirect_returns_302_with_location(client):
    url = unique_url()
    code = create_link(client, url=url)["code"]
    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["location"] == url


@pytest.mark.stage1
def test_unknown_code_returns_404(client):
    r = client.get(f"/{unique_code()}", follow_redirects=False)
    assert r.status_code == 404


@pytest.mark.stage1
def test_missing_url_returns_422(client):
    r = client.post("/links", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------- stage 2


@pytest.mark.stage2
def test_clicks_increment_only_on_redirects(client):
    code = create_link(client)["code"]

    r = client.get(f"/links/{code}")
    assert r.status_code == 200
    assert r.json()["clicks"] == 0  # reading stats must not count as a click

    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)

    r = client.get(f"/links/{code}")
    assert r.json()["clicks"] == 3


@pytest.mark.stage2
def test_stats_for_unknown_code_returns_404(client):
    r = client.get(f"/links/{unique_code()}")
    assert r.status_code == 404


# ---------------------------------------------------------------- stage 3


@pytest.mark.stage3
def test_custom_alias_is_used_as_the_code(client):
    alias = f"wilson-{uuid.uuid4().hex[:8]}"
    body = create_link(client, custom_code=alias)
    assert body["code"] == alias

    r = client.get(f"/{alias}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == body["url"]


@pytest.mark.stage3
def test_custom_alias_collision_returns_409(client):
    alias = f"taken-{uuid.uuid4().hex[:8]}"
    create_link(client, custom_code=alias)
    r = client.post(
        "/links", json={"url": unique_url(), "custom_code": alias}
    )
    assert r.status_code == 409


# ---------------------------------------------------------------- stage 4


@pytest.mark.stage4
def test_patch_changes_destination_and_keeps_clicks(client):
    code = create_link(client)["code"]
    client.get(f"/{code}", follow_redirects=False)  # 1 click

    new_url = unique_url()
    r = client.patch(f"/links/{code}", json={"url": new_url})
    assert r.status_code == 200, r.text
    assert r.json()["url"] == new_url

    r = client.get(f"/{code}", follow_redirects=False)
    assert r.headers["location"] == new_url
    # Two redirects happened in total (one before the edit, one after) — both must
    # survive the edit. A PATCH that resets clicks (e.g. delete + re-insert) would show 1.
    assert client.get(f"/links/{code}").json()["clicks"] == 2


@pytest.mark.stage4
def test_patch_unknown_code_returns_404(client):
    r = client.patch(f"/links/{unique_code()}", json={"url": unique_url()})
    assert r.status_code == 404


@pytest.mark.stage4
def test_delete_returns_204_then_link_is_gone(client):
    code = create_link(client)["code"]
    r = client.delete(f"/links/{code}")
    assert r.status_code == 204

    assert client.get(f"/{code}", follow_redirects=False).status_code == 404
    assert client.get(f"/links/{code}").status_code == 404


@pytest.mark.stage4
def test_delete_unknown_code_returns_404(client):
    r = client.delete(f"/links/{unique_code()}")
    assert r.status_code == 404


# ---------------------------------------------------------------- stage 5


@pytest.mark.stage5
def test_expired_link_returns_410(client):
    body = create_link(client, expires_at="1999-01-01T00:00:00")
    r = client.get(f"/{body['code']}", follow_redirects=False)
    assert r.status_code == 410


@pytest.mark.stage5
def test_future_expiry_still_redirects(client):
    body = create_link(client, expires_at="2099-01-01T00:00:00")
    r = client.get(f"/{body['code']}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == body["url"]
