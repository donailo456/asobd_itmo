"""Load CSV through clickhouse-client in the running Docker container."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "dim_realty", "dim_gauges", "dim_tariffs", "dim_users",
    "fact_gauge_bindings", "fact_meter_readings", "fact_invoice",
)
for table in TABLES:
    path = ROOT / "data" / f"{table}.csv"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run make gen first")

# A clean reload also avoids MergeTree invoice duplicates and preserves CSV
# correction pairs for ReplacingMergeTree.
for table in reversed(TABLES):
    subprocess.run(("docker", "compose", "--env-file", ".env.local", "exec", "-T",
                    "clickhouse", "clickhouse-client", "--query",
                    f"TRUNCATE TABLE energosbyt.{table}"), cwd=ROOT, check=True)
for table in TABLES:
    path = ROOT / "data" / f"{table}.csv"
    print("Loading", table, flush=True)
    with path.open("rb") as f:
        subprocess.run(("docker", "compose", "--env-file", ".env.local", "exec", "-T",
                        "clickhouse", "clickhouse-client", "--query",
                        f"INSERT INTO energosbyt.{table} FORMAT CSV"),
                       stdin=f, cwd=ROOT, check=True)
