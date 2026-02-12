from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logging_setup import setup_logger

SQLITE_PATH = Path("data/app.db")

# --------- Public API (what app.py uses) ---------


class Storage:
    def init(self) -> None: ...
    def backend_name(self) -> str: ...

    def add_person(
        self, user_id: str, name: str, relationship: str, note: str | None
    ) -> None: ...

    def list_people(self, user_id: str) -> List[Dict[str, Any]]: ...

    def add_rating(
        self,
        user_id: str,
        poem_name: str,
        version_label: str,
        request: Dict[str, Any],
        poem_text: str,
        rating: int,
        ending_pref: Optional[str],
        feedback: Optional[str],
    ) -> int: ...

    def list_ratings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]: ...

    def get_version_averages(
        self, user_id: str, poem_name: str
    ) -> Dict[str, Dict[str, Any]]: ...

    def update_taste_profile(
        self,
        user_id: str,
        request: Dict[str, Any],
        rating: int,
        ending_pref: Optional[str],
    ) -> None: ...

    def get_taste_profile(self, user_id: str) -> Dict[str, Any]: ...


def get_storage() -> Storage:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url:
        return PostgresStorage(db_url)
    return SQLiteStorage(SQLITE_PATH)


# --------- SQLite implementation (local fallback) ---------


@dataclass
class SQLiteStorage(Storage):
    path: Path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def backend_name(self) -> str:
        return f"sqlite:{self.path}"

    def init(self) -> None:
        logger = setup_logger()
        with self._connect() as conn:
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                relationship TEXT NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
            )
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                poem_name TEXT NOT NULL,
                version_label TEXT NOT NULL,
                request_json TEXT NOT NULL,
                poem_text TEXT NOT NULL,
                rating INTEGER NOT NULL,
                ending_pref TEXT,
                feedback TEXT
            );
            """
            )
            conn.execute(
                """
            CREATE TABLE IF NOT EXISTS taste_profile (
                user_id TEXT PRIMARY KEY,
                total_ratings INTEGER NOT NULL DEFAULT 0,

                prefer_rhyme_score REAL NOT NULL DEFAULT 0.0,
                avg_line_count REAL NOT NULL DEFAULT 0.0,

                reading_simple_count INTEGER NOT NULL DEFAULT 0,
                reading_general_count INTEGER NOT NULL DEFAULT 0,
                reading_advanced_count INTEGER NOT NULL DEFAULT 0,

                ending_soft_count INTEGER NOT NULL DEFAULT 0,
                ending_twist_count INTEGER NOT NULL DEFAULT 0,
                ending_punchline_count INTEGER NOT NULL DEFAULT 0,
                ending_hopeful_count INTEGER NOT NULL DEFAULT 0,

                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
            )
        logger.info(f"Storage initialized ({self.backend_name()})")

    def add_person(
        self, user_id: str, name: str, relationship: str, note: str | None
    ) -> None:
        name = name.strip()
        relationship = relationship.strip()
        if not name:
            raise ValueError("Person name is required.")
        if not relationship:
            raise ValueError("Relationship is required.")

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO people(user_id, name, relationship, note) VALUES(?,?,?,?)",
                (user_id, name, relationship, note.strip() if note else None),
            )

    def list_people(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, relationship, note, created_at FROM people WHERE user_id=? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def add_rating(
        self,
        user_id: str,
        poem_name: str,
        version_label: str,
        request: Dict[str, Any],
        poem_text: str,
        rating: int,
        ending_pref: Optional[str],
        feedback: Optional[str],
    ) -> int:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be 1..5")

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ratings(user_id, poem_name, version_label, request_json, poem_text, rating, ending_pref, feedback)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    user_id,
                    poem_name.strip() or "Untitled",
                    version_label,
                    json.dumps(request, ensure_ascii=False),
                    poem_text,
                    rating,
                    ending_pref,
                    feedback.strip() if feedback else None,
                ),
            )
            return int(cur.lastrowid)

    def list_ratings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        limit = int(limit)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, poem_name, version_label, rating, ending_pref, feedback
                FROM ratings
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_version_averages(
        self, user_id: str, poem_name: str
    ) -> Dict[str, Dict[str, Any]]:
        poem_name = poem_name.strip() or "Untitled"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT version_label, AVG(rating) AS avg_rating, COUNT(*) AS cnt
                FROM ratings
                WHERE user_id=? AND poem_name=?
                GROUP BY version_label
                """,
                (user_id, poem_name),
            ).fetchall()

        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            out[str(r["version_label"])] = {
                "avg": float(r["avg_rating"]) if r["avg_rating"] is not None else None,
                "count": int(r["cnt"]),
            }
        return out

    def update_taste_profile(
        self,
        user_id: str,
        request: Dict[str, Any],
        rating: int,
        ending_pref: Optional[str],
    ) -> None:
        rhyme = bool(request.get("rhyme", False))
        line_count = int(request.get("line_count", 12))
        reading_level = (request.get("reading_level") or "general").lower()

        strength = rating - 3  # 1->-2, 3->0, 5->+2
        rhyme_delta = float(strength if rhyme else -strength)

        ending = (ending_pref or "").lower().strip()
        ending_col = {
            "soft": "ending_soft_count",
            "twist": "ending_twist_count",
            "punchline": "ending_punchline_count",
            "hopeful": "ending_hopeful_count",
        }.get(ending)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO taste_profile(user_id, total_ratings) VALUES(?,0) ON CONFLICT(user_id) DO NOTHING",
                (user_id,),
            )

            row = conn.execute(
                "SELECT total_ratings, prefer_rhyme_score, avg_line_count, reading_simple_count, reading_general_count, reading_advanced_count, "
                "ending_soft_count, ending_twist_count, ending_punchline_count, ending_hopeful_count "
                "FROM taste_profile WHERE user_id=?",
                (user_id,),
            ).fetchone()

            total = int(row["total_ratings"])
            new_total = total + 1

            prev_avg = float(row["avg_line_count"])
            new_avg = (prev_avg * total + line_count) / new_total

            new_rhyme_score = float(row["prefer_rhyme_score"]) + rhyme_delta

            simple = int(row["reading_simple_count"])
            general = int(row["reading_general_count"])
            advanced = int(row["reading_advanced_count"])
            if reading_level == "simple":
                simple += 1
            elif reading_level == "advanced":
                advanced += 1
            else:
                general += 1

            soft = int(row["ending_soft_count"])
            twist = int(row["ending_twist_count"])
            punch = int(row["ending_punchline_count"])
            hopeful = int(row["ending_hopeful_count"])
            if ending_col == "ending_soft_count":
                soft += 1
            elif ending_col == "ending_twist_count":
                twist += 1
            elif ending_col == "ending_punchline_count":
                punch += 1
            elif ending_col == "ending_hopeful_count":
                hopeful += 1

            conn.execute(
                """
                UPDATE taste_profile SET
                    total_ratings=?,
                    prefer_rhyme_score=?,
                    avg_line_count=?,
                    reading_simple_count=?,
                    reading_general_count=?,
                    reading_advanced_count=?,
                    ending_soft_count=?,
                    ending_twist_count=?,
                    ending_punchline_count=?,
                    ending_hopeful_count=?,
                    updated_at=datetime('now')
                WHERE user_id=?
                """,
                (
                    new_total,
                    new_rhyme_score,
                    new_avg,
                    simple,
                    general,
                    advanced,
                    soft,
                    twist,
                    punch,
                    hopeful,
                    user_id,
                ),
            )

    def get_taste_profile(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM taste_profile WHERE user_id=?",
                (user_id,),
            ).fetchone()

        if not row:
            return {
                "total_ratings": 0,
                "prefer_rhyme_score": 0.0,
                "avg_line_count": None,
                "reading_level_guess": None,
                "ending_guess": None,
            }

        total = int(row["total_ratings"])
        reading_counts = {
            "simple": int(row["reading_simple_count"]),
            "general": int(row["reading_general_count"]),
            "advanced": int(row["reading_advanced_count"]),
        }
        reading_guess = max(reading_counts, key=reading_counts.get) if total > 0 else None

        ending_counts = {
            "soft": int(row["ending_soft_count"]),
            "twist": int(row["ending_twist_count"]),
            "punchline": int(row["ending_punchline_count"]),
            "hopeful": int(row["ending_hopeful_count"]),
        }
        ending_guess = max(ending_counts, key=ending_counts.get) if total > 0 else None

        return {
            "total_ratings": total,
            "prefer_rhyme_score": float(row["prefer_rhyme_score"]),
            "avg_line_count": float(row["avg_line_count"]),
            "reading_level_guess": reading_guess,
            "ending_guess": ending_guess,
            "reading_counts": reading_counts,
            "ending_counts": ending_counts,
        }


# --------- Postgres implementation (Supabase) ---------


@dataclass
class PostgresStorage(Storage):
    database_url: str

    def backend_name(self) -> str:
        return "postgres:DATABASE_URL"

    def _connect(self):
        try:
            import psycopg
        except Exception as e:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg is not installed. Add psycopg[binary] to requirements.txt."
            ) from e
        return psycopg.connect(self.database_url)

    def init(self) -> None:
        logger = setup_logger()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                CREATE TABLE IF NOT EXISTS people (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    note TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                """
                )
                cur.execute(
                    """
                CREATE TABLE IF NOT EXISTS ratings (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    poem_name TEXT NOT NULL,
                    version_label TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    poem_text TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    ending_pref TEXT,
                    feedback TEXT
                );
                """
                )
                cur.execute(
                    """
                CREATE TABLE IF NOT EXISTS taste_profile (
                    user_id TEXT PRIMARY KEY,
                    total_ratings INTEGER NOT NULL DEFAULT 0,

                    prefer_rhyme_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    avg_line_count DOUBLE PRECISION NOT NULL DEFAULT 0.0,

                    reading_simple_count INTEGER NOT NULL DEFAULT 0,
                    reading_general_count INTEGER NOT NULL DEFAULT 0,
                    reading_advanced_count INTEGER NOT NULL DEFAULT 0,

                    ending_soft_count INTEGER NOT NULL DEFAULT 0,
                    ending_twist_count INTEGER NOT NULL DEFAULT 0,
                    ending_punchline_count INTEGER NOT NULL DEFAULT 0,
                    ending_hopeful_count INTEGER NOT NULL DEFAULT 0,

                    updated_at TIMESTAMPTZ DEFAULT now()
                );
                """
                )
            conn.commit()
        logger.info(f"Storage initialized ({self.backend_name()})")

    def add_person(
        self, user_id: str, name: str, relationship: str, note: str | None
    ) -> None:
        name = name.strip()
        relationship = relationship.strip()
        if not name:
            raise ValueError("Person name is required.")
        if not relationship:
            raise ValueError("Relationship is required.")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO people(user_id, name, relationship, note) VALUES(%s,%s,%s,%s)",
                    (user_id, name, relationship, note.strip() if note else None),
                )
            conn.commit()

    def list_people(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, relationship, note, created_at FROM people WHERE user_id=%s ORDER BY id DESC",
                    (user_id,),
                )
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    def add_rating(
        self,
        user_id: str,
        poem_name: str,
        version_label: str,
        request: Dict[str, Any],
        poem_text: str,
        rating: int,
        ending_pref: Optional[str],
        feedback: Optional[str],
    ) -> int:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be 1..5")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ratings(user_id, poem_name, version_label, request_json, poem_text, rating, ending_pref, feedback)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        poem_name.strip() or "Untitled",
                        version_label,
                        json.dumps(request, ensure_ascii=False),
                        poem_text,
                        rating,
                        ending_pref,
                        feedback.strip() if feedback else None,
                    ),
                )
                new_id = cur.fetchone()[0]
            conn.commit()
        return int(new_id)

    def list_ratings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        limit = int(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT created_at, poem_name, version_label, rating, ending_pref, feedback
                    FROM ratings
                    WHERE user_id=%s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    d    def get_version_averages(
        self, user_id: str, poem_name: str
    ) -> Dict[str, Dict[str, Any]]:
        poem_name = poem_name.strip() or "Untitled"

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT version_label, AVG(rating) AS avg_rating, COUNT(*) AS cnt
                    FROM ratings
                    WHERE user_id=%s AND poem_name=%s
                    GROUP BY version_label
                    """,
                    (user_id, poem_name),
                )
                rows = cur.fetchall()

        out: Dict[str, Dict[str, Any]] = {}
        for version_label, avg_rating, cnt in rows:
            out[str(version_label)] = {
                "avg": float(avg_rating) if avg_rating is not None else None,
                "count": int(cnt),
            }
        return out

    def update_taste_profile(
        self,
        user_id: str,
        request: Dict[str, Any],
        rating: int,
        ending_pref: Optional[str],
    ) -> None:
        rhyme = bool(request.get("rhyme", False))
        line_count = int(request.get("line_count", 12))
        reading_level = (request.get("reading_level") or "general").lower()

        strength = rating - 3
        rhyme_delta = float(strength if rhyme else -strength)
        ending = (ending_pref or "").lower().strip()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO taste_profile(user_id, total_ratings) VALUES(%s,0) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,),
                )
                cur.execute(
                    """
                    SELECT total_ratings, prefer_rhyme_score, avg_line_count,
                           reading_simple_count, reading_general_count, reading_advanced_count,
                           ending_soft_count, ending_twist_count, ending_punchline_count, ending_hopeful_count
                    FROM taste_profile WHERE user_id=%s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                (
                    total,
                    prefer_rhyme_score,
                    avg_line_count,
                    rs,
                    rg,
                    ra,
                    es,
                    et,
                    ep,
                    eh,
                ) = row

                total = int(total)
                new_total = total + 1
                new_avg = (float(avg_line_count) * total + line_count) / new_total
                new_rhyme_score = float(prefer_rhyme_score) + rhyme_delta

                if reading_level == "simple":
                    rs += 1
                elif reading_level == "advanced":
                    ra += 1
                else:
                    rg += 1

                if ending == "soft":
                    es += 1
                elif ending == "twist":
                    et += 1
                elif ending == "punchline":
                    ep += 1
                elif ending == "hopeful":
                    eh += 1

                cur.execute(
                    """
                    UPDATE taste_profile SET
                        total_ratings=%s,
                        prefer_rhyme_score=%s,
                        avg_line_count=%s,
                        reading_simple_count=%s,
                        reading_general_count=%s,
                        reading_advanced_count=%s,
                        ending_soft_count=%s,
                        ending_twist_count=%s,
                        ending_punchline_count=%s,
                        ending_hopeful_count=%s,
                        updated_at=now()
                    WHERE user_id=%s
                    """,
                    (
                        new_total,
                        new_rhyme_score,
                        new_avg,
                        rs,
                        rg,
                        ra,
                        es,
                        et,
                        ep,
                        eh,
                        user_id,
                    ),
                )
            conn.commit()

    def get_taste_profile(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM taste_profile WHERE user_id=%s", (user_id,))
                row = cur.fetchone()
                if not row:
                    return {
                        "total_ratings": 0,
                        "prefer_rhyme_score": 0.0,
                        "avg_line_count": None,
                        "reading_level_guess": None,
                        "ending_guess": None,
                    }
                cols = [desc[0] for desc in cur.description]
                data = dict(zip(cols, row))

        total = int(data["total_ratings"])
        reading_counts = {
            "simple": int(data["reading_simple_count"]),
            "general": int(data["reading_general_count"]),
            "advanced": int(data["reading_advanced_count"]),
        }
        reading_guess = max(reading_counts, key=reading_counts.get) if total > 0 else None

        ending_counts = {
            "soft": int(data["ending_soft_count"]),
            "twist": int(data["ending_twist_count"]),
            "punchline": int(data["ending_punchline_count"]),
            "hopeful": int(data["ending_hopeful_count"]),
        }
        ending_guess = max(ending_counts, key=ending_counts.get) if total > 0 else None

        return {
            "total_ratings": total,
            "prefer_rhyme_score": float(data["prefer_rhyme_score"]),
            "avg_line_count": float(data["avg_line_count"]),
            "reading_level_guess": reading_guess,
            "ending_guess": ending_guess,
            "reading_counts": reading_counts,
            "ending_counts": ending_counts,
        }
