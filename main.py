"""
Hiking Buddies Event System
Created by Joseph Timmons
Version 1.0.0
Purpose: Structured and searchable hike listings
"""

from __future__ import annotations

import os
import re
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlmodel import SQLModel, Field, Session, create_engine, select


# --- Anchor paths to this file (prevents template/db “wrong folder” issues) ---
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DB_PATH = BASE_DIR / "hikingbuddies.db"

app = FastAPI()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"
engine = create_engine(DATABASE_URL, echo=False)


# ---------------------------
# Database Models
# ---------------------------

class Mountain(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    mountain_id: int = Field(foreign_key="mountain.id")
    start_date: date

    arrive_time: Optional[time] = None
    hike_time: Optional[time] = None

    trailhead: Optional[str] = None
    distance_miles: float

    pace: str
    dog_friendly: bool

    fb_link: str
    organizer: Optional[str] = None
    notes: Optional[str] = None


SQLModel.metadata.create_all(engine)


# ---------------------------
# Seed Mountains (runs once)
# ---------------------------

MOUNTAIN_NAMES = [
    "Artist’s Bluff","Bald Mountain","Black Mountain","Blue Job Mountain",
    "Bondcliff","Cannon Mountain","Carter Dome","Cherry Mountain",
    "Crotched Mountain","Dickey Mountain","East Osceola",
    "East Rattlesnake Mountain","Galehead Mountain",
    "Middle Carter Mountain","Middle Moat Mountain","Middle Sugarloaf",
    "Middle Tripyramid","Mount Adams","Mount Agamenticus",
    "Mount Belknap","Mount Bond","Mount Cabot","Mount Cardigan",
    "Mount Carrigain","Mount Chocorua","Mount Crawford",
    "Mount Eisenhower","Mount Field","Mount Flume","Mount Garfield",
    "Mount Gunstock","Mount Hale","Mount Hancock","Mount Hayes",
    "Mount Hight","Mount Isolation","Mount Israel","Mount Jackson",
    "Mount Jefferson","Mount Kearsarge","Mount Lafayette",
    "Mount Liberty","Mount Lincoln","Mount Madison","Mount Major",
    "Mount Martha","Mount Moosilauke","Mount Monroe","Mount Moriah",
    "Mount Morgan","Mount Monadnock","Mount Parker",
    "Mount Passaconaway","Mount Pawtuckaway","Mount Pemigewasset",
    "Mount Percival","Mount Pickering","Mount Pierce","Mount Resolution",
    "Mount Roberts","Mount Shaw","Mount Stanton","Mount Starr King",
    "Mount Success","Mount Sunapee","Mount Tecumseh","Mount Tom",
    "Mount Waumbek","Mount Washington","Mount Whiteface",
    "Mount Willard","Mount Willey","Mount Zealand",
    "North Baldface","North Kinsman Mountain","North Moat Mountain",
    "North Pack Monadnock","North Sugarloaf","North Tripyramid",
    "North Twin Mountain","Owl's Head","Pack Monadnock",
    "Ragged Mountain","South Baldface","South Carter Mountain",
    "South Hancock Mountain","South Kinsman Mountain",
    "South Moat Mountain","South Twin Mountain","Welch Mountain",
    "West Bond Mountain","West Rattlesnake Mountain",
    "Wildcat Mountain (A Peak)","Wildcat Mountain (D Peak)"
]

with Session(engine) as session:
    existing = session.exec(select(Mountain)).first()
    if not existing:
        for name in sorted(MOUNTAIN_NAMES):
            session.add(Mountain(name=name))
        session.commit()


# ---------------------------
# Pace Options
# ---------------------------

PACE_CHOICES = ["Turtle", "Bear", "Moose", "GOAT"]


# ---------------------------
# Parsing Helpers
# ---------------------------

def parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def parse_time(s: str) -> Optional[time]:
    raw = (s or "").strip().lower()
    if not raw:
        return None
    raw = raw.replace(" ", "")
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def parse_distance(s: str) -> Optional[float]:
    try:
        return float(re.findall(r"\d+\.?\d*", s)[0])
    except Exception:
        return None


def parse_dog(s: str) -> Optional[bool]:
    raw = (s or "").strip().lower()
    if raw == "yes":
        return True
    if raw == "no":
        return False
    return None


def parse_pace(s: str) -> Optional[str]:
    raw = (s or "").strip().lower()
    mapping = {"turtle": "Turtle", "bear": "Bear", "moose": "Moose", "goat": "GOAT"}
    return mapping.get(raw)


def parse_block(raw: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    parsed: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    lines = [line.strip() for line in raw.splitlines() if ":" in line]

    for line in lines:
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()

        if key.startswith("organizer"):
            parsed["organizer"] = val
        elif key.startswith("mountain"):
            parsed["mountain"] = val
        elif key.startswith("start"):
            parsed["start_date"] = parse_date(val)
        elif key.startswith(("arrive", "arrival", "meet", "meetup")):
            parsed["arrive_time"] = parse_time(val)
        elif key.startswith(("hike", "start time", "begin")):
            parsed["hike_time"] = parse_time(val)
        elif key.startswith("trailhead"):
            parsed["trailhead"] = val
        elif key.startswith("distance"):
            parsed["distance_miles"] = parse_distance(val)
        elif key.startswith("pace"):
            parsed["pace"] = parse_pace(val)
        elif key.startswith("dog"):
            parsed["dog_friendly"] = parse_dog(val)
        elif key.startswith("fb"):
            parsed["fb_link"] = val.split()[0]
        elif key.startswith("notes"):
            parsed["notes"] = val

    return parsed, errors

# Add Event Key

ADD_EVENT_KEY = os.getenv("ADD_EVENT_KEY", "").strip()

def require_add_key(request: Request) -> None:
    if not ADD_EVENT_KEY:
        return  # allow if not set (nice for local dev)
    if request.query_params.get("key", "") != ADD_EVENT_KEY:
        # 404 instead of 401 so it doesn't advertise that /add exists
        raise HTTPException(status_code=404, detail="Not found")

# ---------------------------
# Routes
# ---------------------------

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/events", status_code=302)


@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request):
    require_add_key(request)

    with Session(engine) as session:
        mountains = session.exec(select(Mountain).order_by(Mountain.name)).all()

    return templates.TemplateResponse(
        "add.html",
        {
            "request": request,
            "mountains": mountains,
            "pace_choices": PACE_CHOICES,
            "parsed": {},
            "errors": {},
            "raw": "",
        },
    )


@app.post("/add", response_class=HTMLResponse)
def fill_form(request: Request, raw: str = Form(...)):
    require_add_key(request)

    parsed, errors = parse_block(raw)

    with Session(engine) as session:
        mountains = session.exec(select(Mountain).order_by(Mountain.name)).all()

    return templates.TemplateResponse(
        "add.html",
        {
            "request": request,
            "mountains": mountains,
            "pace_choices": PACE_CHOICES,
            "parsed": parsed,
            "errors": errors,
            "raw": raw,
        },
    )

@app.post("/events")
def create_event(
    mountain_id: int = Form(...),
    start_date: str = Form(...),
    arrive_time: str = Form(""),
    hike_time: str = Form(""),
    trailhead: str = Form(""),
    distance_miles: str = Form(...),
    pace: str = Form(...),
    dog_friendly: str = Form(...),
    fb_link: str = Form(...),
    organizer: str = Form(""),
    notes: str = Form(""),
):
    start_dt = parse_date(start_date)
    if start_dt is None:
        raise HTTPException(status_code=400, detail="Invalid start date. Use YYYY-MM-DD.")

    dog_bool = parse_dog(dog_friendly)
    if dog_bool is None:
        raise HTTPException(status_code=400, detail="Dog Friendly must be Yes or No.")

    try:
        dist = float(distance_miles)
    except Exception:
        raise HTTPException(status_code=400, detail="Distance must be a number.")

    # Normalize pace casing (optional but keeps data consistent)
    mapping = {"turtle": "Turtle", "bear": "Bear", "moose": "Moose", "goat": "GOAT"}
    pace_norm = mapping.get((pace or "").strip().lower(), pace)

    with Session(engine) as session:
        event = Event(
            mountain_id=mountain_id,
            start_date=start_dt,
            arrive_time=parse_time(arrive_time) if arrive_time else None,
            hike_time=parse_time(hike_time) if hike_time else None,
            trailhead=trailhead or None,
            distance_miles=dist,
            pace=pace_norm,
            dog_friendly=dog_bool,
            fb_link=fb_link,
            organizer=organizer or None,
            notes=notes or None,
        )
        session.add(event)
        session.commit()

    return RedirectResponse("/events", status_code=303)


@app.get("/events", response_class=HTMLResponse)
def list_events(
    request: Request,
    mountain_id: str | None = Query(default=None),
    pace: str | None = Query(default=None),
    max_miles: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    dog_friendly: str | None = Query(default=None),
):
    # Safely convert optional numeric filters
    mountain_id_int: int | None = None
    if mountain_id and mountain_id.strip() != "":
        try:
            mountain_id_int = int(mountain_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid mountain selection.")

    max_miles_float: float | None = None
    if max_miles and max_miles.strip() != "":
        try:
            max_miles_float = float(max_miles)
        except ValueError:
            raise HTTPException(status_code=400, detail="Max miles must be a number.")

    date_filter = None
    if start_date and start_date.strip() != "":
        date_filter = parse_date(start_date)
        if date_filter is None:
            raise HTTPException(status_code=400, detail="Invalid date filter. Use YYYY-MM-DD.")

    with Session(engine) as session:
        mountains = session.exec(select(Mountain).order_by(Mountain.name)).all()

        stmt = select(Event, Mountain).join(Mountain, Event.mountain_id == Mountain.id)

        if mountain_id_int is not None:
            stmt = stmt.where(Event.mountain_id == mountain_id_int)

        if pace:
            stmt = stmt.where(Event.pace == pace)

        if max_miles_float is not None:
            stmt = stmt.where(Event.distance_miles <= max_miles_float)

        if date_filter is not None:
            stmt = stmt.where(Event.start_date == date_filter)

        if dog_friendly in ("Yes", "No"):
            stmt = stmt.where(Event.dog_friendly == (dog_friendly == "Yes"))

        stmt = stmt.order_by(Event.start_date)

        result = session.exec(stmt).all()

    rows: List[Tuple[Event, Mountain]] = []
    for r in result:
        if isinstance(r, tuple) and len(r) == 2:
            rows.append((r[0], r[1]))
        else:
            rows.append((r.Event, r.Mountain))

    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "rows": rows,
            "mountains": mountains,
            "pace_choices": PACE_CHOICES,
            "filters": {
                "mountain_id": mountain_id or "",
                "pace": pace or "",
                "max_miles": max_miles or "",
                "start_date": start_date or "",
                "dog_friendly": dog_friendly or "",
            },
        },
    )