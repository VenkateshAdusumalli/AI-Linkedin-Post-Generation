import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


DATABASE_PATH = Path(__file__).resolve().parent / "videos.db"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def init_database() -> None:
    """Create the video tracking table when it does not already exist."""
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                video_id TEXT UNIQUE,
                video_title TEXT,
                published_at TEXT,
                processed_at TEXT
            )
            """
        )


def is_video_processed(video_id: str) -> bool:
    """Return whether a video has already completed processing."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM videos WHERE video_id = ? LIMIT 1",
            (video_id,),
        ).fetchone()
    return row is not None


def save_processed_video(
    channel_id: str,
    video_id: str,
    video_title: str,
    published_at: str | None,
) -> None:
    """Record a successfully processed video without creating duplicates."""
    processed_at = datetime.now().isoformat(timespec="seconds")
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO videos (
                channel_id,
                video_id,
                video_title,
                published_at,
                processed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (channel_id, video_id, video_title, published_at, processed_at),
        )
