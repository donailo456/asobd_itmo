"""Deterministic, dependency-free CSV generator for laboratory work 1."""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
START = date(2023, 11, 1)
END = date(2026, 10, 31)
NOW = "2023-10-01 00:00:00"
CHANGE = date(2025, 1, 1)


def output(table):
    return (DATA / (table + ".csv")).open("w", newline="", encoding="utf-8")


def tariff(day):
    if day >= date(2026, 7, 1):
        return 620, 310
    if day >= date(2025, 11, 1):
        return 570, 285
    return 500, 250


with output("dim_realty") as f:
    w = csv.writer(f)
    for i in range(1, 1001):
        nonresidential = i % 10 == 0
        w.writerow((i, f"г. Москва, ул. Энергетиков, д. {(i - 1) // 100 + 1}",
                    30 + i % 75, "nrcp" if nonresidential else "flat",
                    "" if nonresidential else str(i), 0 if nonresidential else i % 4 + 1,
                    i % 20 + 1, i % 5 + 1, NOW))

with output("dim_gauges") as f:
    w = csv.writer(f)
    for i in range(1, 1101):
        w.writerow((i, "Меркурий-" + str(i % 5 + 200), "Россия", NOW))

with output("dim_users") as f:
    w = csv.writer(f)
    for i in range(1, 1001):
        w.writerow((i, f"Иванов Иван Иванович {i}", f"+7900{i:07d}", "", NOW, NOW))

with output("dim_tariffs") as f:
    w = csv.writer(f)
    for start, end, day_price, night_price in (
        ("2023-11-01 00:00:00", "2025-11-01 00:00:00", 500, 250),
        ("2025-11-01 00:00:00", "2026-07-01 00:00:00", 570, 285),
        ("2026-07-01 00:00:00", "2099-01-01 00:00:00", 620, 310),
    ):
        w.writerow((1, "День–Ночь", day_price, night_price, start, end, NOW, start))

with output("fact_gauge_bindings") as f:
    w = csv.writer(f)
    for i in range(1, 1001):
        w.writerow((i, i, NOW, 1, 1))
        if i <= 100:
            w.writerow((i, i, NOW, -1, 1))
            w.writerow((1000 + i, i, "2025-01-01 00:00:00", 1, 2))

with output("fact_meter_readings") as f:
    w = csv.writer(f)
    day = START
    ordinal = 0
    while day <= END:
        for i in range(1, 1001):
            gauge = i + 1000 if i <= 100 and day >= CHANGE else i
            day_kw, night_kw = 100 + ordinal * 4 + i % 20, 50 + ordinal * 2 + i % 10
            row = (i, i, 1, gauge, day.isoformat(), day_kw, night_kw)
            w.writerow((*row, f"{day} 09:00:00"))
            if (ordinal * 1000 + i) % 33 == 0:
                w.writerow((*row, f"{day} 10:00:00"))
        ordinal += 1
        day += timedelta(days=1)

with output("fact_invoice") as f:
    w = csv.writer(f)
    month = START
    while month <= END:
        next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        days = (next_month - month).days
        day_price, night_price = tariff(month)
        gauge_change = month >= CHANGE
        for i in range(1, 1001):
            gauge = i + 1000 if i <= 100 and gauge_change else i
            day_kw, night_kw = days * 4, days * 2
            w.writerow((i, i, 1, gauge, day_kw, night_kw,
                        day_kw * day_price + night_kw * night_price,
                        (next_month + timedelta(days=9)).isoformat(),
                        f"{month.year}-{month.month:02d}-{days:02d} 10:00:00"))
        month = next_month

print("CSV files generated in", DATA)
