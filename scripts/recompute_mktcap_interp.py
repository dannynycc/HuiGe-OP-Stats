"""Compute daily TWSE mkt_cap via interpolation from weekly + daily TWII.

Logic:
  For each trading date d where twse_mkt_cap_chao IS NULL (and not 'official'):
    - weekly_anchor = nearest mkt_cap_weekly row to d (within +/- 7 days,
      prefer same week, fallback to nearest)
    - daily_mkt_cap_oku = weekly_anchor.oku * (TWII_d / TWII_anchor)
    - daily_mkt_cap_chao = daily_mkt_cap_oku / 10000
    - mark mkt_cap_source = 'interp'

Skipped rows: TWII_d NULL, weekly_anchor not found, mkt_cap_source='official'.
Idempotent — re-running overwrites only 'interp' rows.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect


def find_anchor(con, d: str) -> tuple[str, float] | None:
    """Closest weekly mkt_cap row to date d. Prefers same-week (>= d, within 7d),
    fallback to <= d. Returns (anchor_date, anchor_oku) or None."""
    # Same-week / future side first
    row = con.execute(
        """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
           WHERE date >= ? AND date < date(?, '+8 days')
           ORDER BY date LIMIT 1""",
        (d, d),
    ).fetchone()
    if row:
        return row[0], row[1]
    # Fallback: most recent past anchor
    row = con.execute(
        """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
           WHERE date < ? ORDER BY date DESC LIMIT 1""",
        (d,),
    ).fetchone()
    if row:
        return row[0], row[1]
    return None


def main():
    written = 0
    skipped_no_twii = 0
    skipped_no_anchor = 0
    skipped_official = 0
    skipped_anchor_no_twii = 0

    with connect() as con:
        rows = list(con.execute("""
            SELECT date, twii_close, twse_mkt_cap_chao, mkt_cap_source
            FROM daily_summary ORDER BY date
        """))
        # Pre-build twii index for fast lookup
        twii_map = dict(con.execute(
            "SELECT date, twii_close FROM daily_summary WHERE twii_close IS NOT NULL"
        ).fetchall())

        for r in rows:
            d = r["date"]
            if r["mkt_cap_source"] == "official":
                skipped_official += 1
                continue
            twii_d = r["twii_close"]
            if twii_d is None:
                skipped_no_twii += 1
                continue
            anchor = find_anchor(con, d)
            if not anchor:
                skipped_no_anchor += 1
                continue
            anchor_date, anchor_oku = anchor
            twii_anchor = twii_map.get(anchor_date)
            if twii_anchor is None:
                skipped_anchor_no_twii += 1
                continue
            daily_oku = anchor_oku * (twii_d / twii_anchor)
            daily_chao = daily_oku / 10000.0
            con.execute(
                """UPDATE daily_summary
                   SET twse_mkt_cap_chao = ?, mkt_cap_source = 'interp'
                   WHERE date = ?""",
                (daily_chao, d),
            )
            written += 1

    print(f"Wrote {written} interp rows.")
    print(f"  skipped: official={skipped_official}, no_TWII_d={skipped_no_twii}, "
          f"no_anchor={skipped_no_anchor}, anchor_TWII_null={skipped_anchor_no_twii}")


if __name__ == "__main__":
    main()
