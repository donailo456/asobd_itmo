import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler

from errors import BadRequest, NotFound
from validation import field, parameter, reading, user_changes, valid_id


class Handler(BaseHTTPRequestHandler):
    service = None

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
        except ValueError:
            raise BadRequest("invalid JSON body")

    def dispatch(self):
        parsed = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        method = self.command
        path = parsed.path
        if method == "GET" and path == "/ping":
            return 200, None
        if method == "GET" and path == "/tariffs":
            day = parameter(params, "date")
            return 200, self.service.get_tariff(day)

        match = re.fullmatch(r"/(users|realty)/(\d+)(?:/(readings|invoices|gauges))?", path)
        if not match:
            raise NotFound()
        group, raw_id, child = match.groups()
        item_id = int(raw_id)
        if not valid_id(item_id):
            raise NotFound()

        if group == "users" and child is None:
            if method == "GET":
                return 200, self.service.get_user(item_id)
            if method == "PATCH":
                self.service.update_user(item_id, user_changes(self.body()))
                return 204, None

        if group == "realty":
            if method == "GET" and child is None:
                return 200, self.service.get_realty(item_id)
            if method == "GET" and child == "readings":
                date_from = parameter(params, "date_from")
                date_to = parameter(params, "date_to")
                if date_from > date_to:
                    raise BadRequest('invalid "date_from" parameter')
                return 200, self.service.list_readings(item_id, date_from, date_to)
            if method == "GET" and child == "invoices":
                limit = parameter(params, "limit", "10", "int")
                offset = parameter(params, "offset", "0", "int")
                return 200, self.service.list_invoices(item_id, limit, offset)
            if method == "POST" and child == "readings":
                self.service.create_reading(item_id, reading(self.body()))
                return 201, None
            if method == "POST" and child == "gauges":
                gauge_id = field(self.body(), "gauge_id", valid_id)
                self.service.install_gauge(item_id, gauge_id)
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
