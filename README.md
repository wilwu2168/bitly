# pybitly — a Bitly clone

You write all the code. The test suite is the spec. Ask for hints, never answers.

## Setup (already done once by your coach)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Your job

Create `app/main.py` exposing `app = FastAPI()`. The suite imports it as
`app.main:app`. Read your database path from the environment:

```python
DB_PATH = os.environ.get("DB_PATH", "links.db")
```

(The tests overwrite `DB_PATH` to point at a scratch file — that's how they
stay away from your real data.)

## The contract

| Method & path          | Body                                             | Success | Failure |
|------------------------|--------------------------------------------------|---------|---------|
| `POST /links`          | `{"url", "custom_code"?, "expires_at"?}`         | **201** + `{code, url, clicks}` | 409 alias taken, 422 bad body |
| `GET /{code}`          | —                                                | **302** + `Location: <url>`    | 404 unknown, 410 expired |
| `GET /links/{code}`    | —                                                | **200** + `{code, url, clicks}` | 404 unknown |
| `PATCH /links/{code}`  | `{"url"}`                                        | **200** + updated link         | 404 unknown |
| `DELETE /links/{code}` | —                                                | **204**                        | 404 unknown |

Rules the tests enforce:

- Auto-generated codes are strings, ≤ 16 chars, unique per creation.
- Only `GET /{code}` counts a click; reading stats doesn't.
- Editing a destination preserves its click count.
- `expires_at` is an ISO 8601 datetime; a past one makes the link dead (410).
- Redirect is **302**, never 301 — destinations are editable and clicks are
  counted, so browsers must not cache.

## Run the tests

```bash
pytest -m stage1   # create + redirect core — start here
pytest -m stage2   # click stats
pytest -m stage3   # custom aliases
pytest -m stage4   # edit + delete
pytest -m stage5   # expiration
pytest             # everything
```

## Dev server

```bash
uvicorn app.main:app --reload
```
