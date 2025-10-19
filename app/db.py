import sqlite3
from pathlib import Path
from app.config import DATA_DIR

DB_PATH = DATA_DIR / "app.sqlite"

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS refinements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,          -- 'collection' or 'refinement'
            source_key TEXT NOT NULL,           -- folder name OR refinement_id as text
            status TEXT NOT NULL DEFAULT 'active', -- 'active' | 'complete'
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS refinement_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refinement_id INTEGER NOT NULL,
            relpath TEXT NOT NULL,              -- file name within the source
            rating TEXT,                        -- 'yes' | 'no' | 'skip' | NULL (pending)
            FOREIGN KEY(refinement_id) REFERENCES refinements(id) ON DELETE CASCADE
        );
        """)
