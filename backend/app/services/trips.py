"""Trip persistence service — SQLite-backed storage with shareable links."""

import json
import logging
import os
import secrets
import sqlite3
import string
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Short ID alphabet: URL-safe, no ambiguous chars (0/O, 1/l/I)
_ALPHABET = string.ascii_lowercase + string.digits
_ID_LENGTH = 8

DB_PATH = os.getenv("TRIPS_DB_PATH", str(Path(__file__).parent.parent.parent / "data" / "trips.db"))


def _generate_short_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_ID_LENGTH))


def _get_db() -> sqlite3.Connection:
    """Get a SQLite connection, creating the DB and table if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            itinerary_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            transport_mode TEXT,
            time_constraint TEXT,
            total_days INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def save_trip(itinerary_dict: dict) -> str:
    """Save an itinerary and return its short ID for sharing."""
    trip_id = _generate_short_id()
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO trips (id, city, itinerary_json, created_at, transport_mode, time_constraint, total_days)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trip_id,
                itinerary_dict.get("city", "Unknown"),
                json.dumps(itinerary_dict),
                datetime.now(timezone.utc).isoformat(),
                itinerary_dict.get("transport_mode"),
                itinerary_dict.get("time_constraint"),
                itinerary_dict.get("total_days", 1),
            ),
        )
        conn.commit()
        logger.info(f"[Trips] Saved trip {trip_id} for {itinerary_dict.get('city')}")
        return trip_id
    finally:
        conn.close()


def get_trip(trip_id: str) -> dict | None:
    """Retrieve a trip by its short ID. Returns None if not found."""
    conn = _get_db()
    try:
        row = conn.execute("SELECT itinerary_json FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row:
            return json.loads(row["itinerary_json"])
        return None
    finally:
        conn.close()


def list_recent_trips(limit: int = 20) -> list[dict]:
    """List recent trips (metadata only, not full itinerary)."""
    conn = _get_db()
    try:
        rows = conn.execute(
            """SELECT id, city, created_at, transport_mode, total_days
               FROM trips ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
