import sqlite3
from pathlib import Path
from approval.core.models import Extraction

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, result TEXT NOT NULL);
        """)

    def get(self, key):
        row = self.db.execute("SELECT payload FROM checkpoints WHERE key=?", (key,)).fetchone()
        return Extraction.model_validate_json(row[0]) if row else None

    def put(self, key, extraction):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?)", (key, extraction.model_dump_json()))

    def save_run(self, result):
        with self.db:
            self.db.execute("INSERT INTO runs VALUES (?,?)", (result.run_id, result.model_dump_json()))

    def close(self): self.db.close()
