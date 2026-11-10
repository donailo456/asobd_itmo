"""Small stdlib-only JSON API backed by ClickHouse HTTP."""
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
PORT = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
USER = os.getenv("CLICKHOUSE_USER", "default")
PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
DATABASE = os.getenv("CLICKHOUSE_DATABASE", "energosbyt")
LOCK = threading.RLock()


def literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def query(sql):
    url = f"http://{HOST}:{PORT}/?" + urllib.parse.urlencode({
        "database": DATABASE, "output_format_json_quote_64bit_integers": "0"})
    request = urllib.request.Request(url, data=sql.encode(), method="POST")
    import base64
    credentials = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request.add_header("Authorization", "Basic " + credentials)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    if sql.lstrip().upper().startswith("SELECT"):
        return json.loads(raw).get("data", [])
    return []


def rows(sql):
    return query(sql + " FORMAT JSON")


def one(sql):
    values = rows(sql)
    return values[0] if values else None


def exists(table, id_):
    final = " FINAL" if table in ("dim_users", "dim_tariffs") else ""
    return one(f"SELECT id FROM {table}{final} WHERE id={id_} LIMIT 1") is not None


def valid_id(value):
    return type(value) is int and 0 < value < 2**64


def valid_uint(value):
    return type(value) is int and 0 <= value < 2**32


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def next_timestamp(last=None):
    now = datetime.now().replace(microsecond=0)
    if last:
        now = max(now, datetime.fromisoformat(last) + timedelta(seconds=1))
    return now.strftime("%Y-%m-%d %H:%M:%S")


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body=None):
        raw = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 65536 or size < 0:
                raise ValueError()
            value = json.loads(self.rfile.read(size))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, json.JSONDecodeError):
            raise BadRequest("invalid JSON body")

    def field(self, body, name, test):
        value = body.get(name)
        if not test(value):
            raise BadRequest(f'invalid "{name}" field')
        return value

    def param(self, params, name, default=None, kind="date"):
        value = params.get(name, [default])[0]
        if kind == "date":
            good = valid_date(value)
        else:
            good = isinstance(value, str) and bool(re.fullmatch(r"\d+", value)) and int(value) < 2**63
        if not good:
            raise BadRequest(f'invalid "{name}" parameter')
        return value if kind == "date" else int(value)

    def dispatch(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        method = self.command
        if method == "GET" and path == "/ping":
            return 200, None
        if method == "GET" and path == "/tariffs":
            day = self.param(params, "date")
            row = one("SELECT id,name,price_day_kwph,price_night_kwph,valid_from,valid_to "
                      "FROM dim_tariffs FINAL WHERE valid_from <= " + literal(day + " 00:00:00") +
                      " AND valid_to > " + literal(day + " 00:00:00") +
                      " ORDER BY valid_from DESC LIMIT 1")
            if row is None:
                raise NotFound()
            return 200, row
        match = re.fullmatch(r"/(users|realty)/(\d+)(?:/(readings|invoices|gauges))?", path)
        if not match:
            raise NotFound()
        group, raw_id, child = match.groups()
        id_ = int(raw_id)
        if not valid_id(id_):
            raise NotFound()
        if group == "users" and child is None:
            if method == "GET":
                row = one(f"SELECT id,fio,phone,phone_prev FROM dim_users FINAL WHERE id={id_} LIMIT 1")
                if row is None:
                    raise NotFound()
                return 200, row
            if method == "PATCH":
                data = self.body()
                if not data or any(k not in ("fio", "phone") for k in data):
                    raise BadRequest('invalid "fio" field')
                for field in data:
                    self.field(data, field, lambda x: isinstance(x, str) and bool(x.strip()))
                with LOCK:
                    current = one(f"SELECT * FROM dim_users FINAL WHERE id={id_} LIMIT 1")
                    if current is None:
                        raise NotFound()
                    fio = data.get("fio", current["fio"])
                    phone = data.get("phone", current["phone"])
                    previous = current["phone"] if phone != current["phone"] else current["phone_prev"]
                    stamp = next_timestamp(current["updated_at"])
                    query("INSERT INTO dim_users (id,fio,phone,phone_prev,created_at,updated_at) VALUES ("
                          f"{id_},{literal(fio)},{literal(phone)},{literal(previous)},"
                          f"{literal(current['created_at'])},{literal(stamp)})")
                return 204, None
        if group == "realty":
            if method == "GET" and child is None:
                row = one("SELECT id,address,square,type,number,rooms,floor,porch "
                          f"FROM dim_realty WHERE id={id_} LIMIT 1")
                if row is None:
                    raise NotFound()
                return 200, row
            if method == "GET" and child == "readings":
                start = self.param(params, "date_from")
                end = self.param(params, "date_to")
                if start > end:
                    raise BadRequest('invalid "date_from" parameter')
                if not exists("dim_realty", id_):
                    raise NotFound()
                values = rows("SELECT reading_date,user_id,tariff_id,gauge_id,day_kw,night_kw "
                              f"FROM fact_meter_readings FINAL WHERE realty_id={id_} "
                              f"AND reading_date BETWEEN {literal(start)} AND {literal(end)} "
                              "ORDER BY reading_date")
                return 200, {"readings": values, "count": len(values)}
            if method == "GET" and child == "invoices":
                limit = self.param(params, "limit", "10", "int")
                offset = self.param(params, "offset", "0", "int")
                if not exists("dim_realty", id_):
                    raise NotFound()
                count = one(f"SELECT count() AS count FROM fact_invoice WHERE realty_id={id_}")["count"]
                values = rows("SELECT tariff_id,gauge_id,day_kw,night_kw,price,deadline,created_at "
                              f"FROM fact_invoice WHERE realty_id={id_} "
                              f"ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}")
                return 200, {"invoices": values, "count": count}
            if method == "POST" and child == "readings":
                data = self.body()
                user = self.field(data, "user_id", valid_id)
                gauge = self.field(data, "gauge_id", valid_id)
                tariff = self.field(data, "tariff_id", valid_id)
                day = self.field(data, "reading_date", valid_date)
                day_kw = self.field(data, "day_kw", valid_uint)
                night_kw = self.field(data, "night_kw", valid_uint)
                if not all((exists("dim_realty", id_), exists("dim_users", user),
                            exists("dim_gauges", gauge), exists("dim_tariffs", tariff))):
                    raise NotFound()
                with LOCK:
                    old = one("SELECT max(created_at) AS stamp FROM fact_meter_readings "
                              f"WHERE realty_id={id_} AND reading_date={literal(day)}")
                    stamp = next_timestamp(old["stamp"])
                    query("INSERT INTO fact_meter_readings "
                          "(realty_id,user_id,tariff_id,gauge_id,reading_date,day_kw,night_kw,created_at) VALUES "
                          f"({id_},{user},{tariff},{gauge},{literal(day)},{day_kw},{night_kw},{literal(stamp)})")
                return 201, None
            if method == "POST" and child == "gauges":
                data = self.body()
                gauge = self.field(data, "gauge_id", valid_id)
                if not exists("dim_realty", id_) or not exists("dim_gauges", gauge):
                    raise NotFound()
                with LOCK:
                    active = one("SELECT gauge_id,created_at,version FROM fact_gauge_bindings FINAL "
                                 f"WHERE realty_id={id_} AND sign=1 ORDER BY version DESC LIMIT 1")
                    maximum = one(f"SELECT max(version) AS version FROM fact_gauge_bindings WHERE realty_id={id_}")
                    version = int(maximum["version"] or 0) + 1
                    if active:
                        query("INSERT INTO fact_gauge_bindings VALUES "
                              f"({active['gauge_id']},{id_},{literal(active['created_at'])},-1,{active['version']})")
                    query("INSERT INTO fact_gauge_bindings VALUES "
                          f"({gauge},{id_},{literal(next_timestamp())},1,{version})")
                return 201, None
        raise NotFound()

    def do_GET(self):
        self.run_request()

    def do_POST(self):
        self.run_request()

    def do_PATCH(self):
        self.run_request()

    def run_request(self):
        try:
            status, body = self.dispatch()
        except BadRequest as exc:
            status, body = 400, {"message": str(exc)}
        except NotFound:
            status, body = 404, {"message": "Not found"}
        except Exception as exc:
            print("Request failed:", repr(exc), flush=True)
            status, body = 503, {"message": "Database unavailable"}
        self.respond(status, body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("APP_PORT", "8080"))), Handler).serve_forever()
