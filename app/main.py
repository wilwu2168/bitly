from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
import random 
import string 
import sqlite3
import os 

app = FastAPI()
DB_PATH = os.environ.get("DB_PATH", "url.db")
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
RETRIEVAL_LOG = LOG_DIR / "retrievals.log"
con = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = con.cursor()

STRING_LENGTH = 6

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class LinkCreate(BaseModel):
### Create a link  
   url: str
   custom_code: str | None = None
   expires_at: datetime | None = None

class LinkOut(BaseModel):
### What we send to the Client
   url: str;
   code: str;
   clicks: int

class LinkUpdate(BaseModel):
   url: str;


def _is_expired(expires_at: str) -> bool:
   expires = datetime.fromisoformat(expires_at)
   if expires.tzinfo is None:
      return expires < datetime.now()
   return expires < datetime.now(timezone.utc)


def log_retrieval(code: str, dest: str, client_ip: str | None = None) -> None:
   LOG_DIR.mkdir(parents=True, exist_ok=True)
   ts = datetime.now(timezone.utc).isoformat()
   ip = client_ip or "-"
   line = f"{ts}\tcode={code}\tdest={dest}\tip={ip}\n"
   with RETRIEVAL_LOG.open("a", encoding="utf-8") as f:
      f.write(line)


@app.get("/")
def home():
   return FileResponse(STATIC_DIR / "index.html")


@app.post("/links", status_code=201, response_model=LinkOut)
def create_link(link: LinkCreate) -> LinkOut:
   letters = string.ascii_letters + string.digits
   if link.custom_code:
      code = link.custom_code
   else:
      code = ''.join(random.choice(letters) for i in range(STRING_LENGTH))
   try: 
      cursor.execute("INSERT INTO links (code, url, clicks, expires_at) values (?, ?, 0, ?)", (code, link.url, link.expires_at.isoformat() if link.expires_at else None),)
   except sqlite3.IntegrityError:
      raise HTTPException(status_code=409, detail="code already taken")

   con.commit()
   return LinkOut(url=link.url, code=code, clicks=0)

@app.get("/{code}")
def redirect(code: str, request: Request):
    row = cursor.execute("SELECT url, expires_at FROM links WHERE code = ?", (code, )).fetchone()
    if row is None:
       raise HTTPException(status_code=404, detail="Not found")
    dest, expires_at = row
    if expires_at is not None and _is_expired(expires_at):
       raise HTTPException(status_code=410, detail="link expired")
    cursor.execute("UPDATE links set clicks = clicks + 1 where code =?", (code,)) 
    con.commit()
    client_ip = request.client.host if request.client else None
    log_retrieval(code, dest, client_ip)
    return RedirectResponse(row[0], status_code=302)

@app.get("/links/{code}")
def get_stats(code: str):
   row = cursor.execute("SELECT code, url, clicks FROM links WHERE code = ?", (code,)).fetchone()
   if row is None:
      raise HTTPException(status_code=404, detail="Not found")
   code, url, clicks = row
   return LinkOut(url=url, code=code, clicks=clicks)

@app.patch("/links/{code}", status_code=200, response_model=LinkOut)
def update(code: str, changes: LinkUpdate):
   row = cursor.execute("SELECT code, url, clicks FROM links where code = ?", (code, )).fetchone()
   if row is None:
      raise HTTPException(status_code=404, detail="Not found")
   cursor.execute("UPDATE links set url = ? WHERE code = ?", (changes.url, code)) 
   con.commit()  
   code, url, clicks = row
   return LinkOut(url=changes.url, code=code, clicks=clicks)
    
@app.delete("/links/{code}", status_code=204)
def delete(code: str):
   row = cursor.execute("SELECT code, url, clicks FROM links where code = ?", (code, )).fetchone()
   if row is None:
      raise HTTPException(status_code=404, detail="Not found")
   cursor.execute("DELETE FROM links where code = ?", (code, ))
   con.commit()
   


### BUILD THE DB

cursor.execute("""
    CREATE TABLE IF NOT EXISTS links ( 
      code  TEXT PRIMARY KEY,
      url TEXT,
      clicks INTEGER DEFAULT 0,
      expires_at TEXT
      )
""")
con.commit()
