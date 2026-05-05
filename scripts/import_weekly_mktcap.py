"""Import TWSE 市值週報 .xls into mkt_cap_weekly table.

Source: https://www.twse.com.tw/zh/trading/statistics/week.html
File format: Excel 97-2003 (.xls), Sheet1 has header rows + (date_serial, mkt_cap_oku) pairs from 2005-09-02 onwards.
"""
import sys
import pathlib
import xlrd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect


def main(xls_path: str) -> None:
    wb = xlrd.open_workbook(xls_path)
    sh = wb.sheet_by_name("Sheet1")
    rows: list[tuple[str, float]] = []
    for r in range(2, sh.nrows):  # skip 2 header rows
        serial = sh.cell_value(r, 0)
        mkt_cap = sh.cell_value(r, 1)
        if not isinstance(serial, (int, float)) or not isinstance(mkt_cap, (int, float)):
            continue
        date = xlrd.xldate_as_datetime(serial, wb.datemode).date().isoformat()
        rows.append((date, float(mkt_cap)))

    print(f"parsed {len(rows)} weekly rows ({rows[0][0]} ~ {rows[-1][0]})")

    with connect() as con:
        for date, oku in rows:
            con.execute(
                "INSERT OR REPLACE INTO mkt_cap_weekly (date, twse_mkt_cap_oku, source) VALUES (?, ?, ?)",
                (date, oku, "twse_weekly_xls"),
            )
        n = con.execute("SELECT COUNT(*) FROM mkt_cap_weekly").fetchone()[0]
    print(f"DB now has {n} weekly rows")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/import_weekly_mktcap.py <path/to/week1-new.xls>")
        sys.exit(1)
    main(sys.argv[1])
