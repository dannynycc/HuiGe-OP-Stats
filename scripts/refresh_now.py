"""CLI: trigger a single refresh (no server)."""
import sys, pathlib, argparse, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.refresh import refresh

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD (defaults to most recent weekday)")
    args = p.parse_args()
    result = refresh(args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
