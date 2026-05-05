"""Initialize SQLite schema."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import init_db, DB_PATH

if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
