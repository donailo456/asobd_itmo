import base64
import json
import os
import urllib.parse
import urllib.request


def literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


class ClickHouseClient:
    def __init__(self):
        host = os.getenv("CLICKHOUSE_HOST", "localhost")
        port = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
        database = os.getenv("CLICKHOUSE_DATABASE", "energosbyt")
        user = os.getenv("CLICKHOUSE_USER", "default")
        password = os.getenv("CLICKHOUSE_PASSWORD", "")
        params = urllib.parse.urlencode({
            "database": database,
            "output_format_json_quote_64bit_integers": "0",
        })
        self.url = f"http://{host}:{port}/?{params}"
        credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.authorization = "Basic " + credentials

    def query(self, sql):
        request = urllib.request.Request(self.url, data=sql.encode(), method="POST")
        request.add_header("Authorization", self.authorization)
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def rows(self, sql):
        return json.loads(self.query(sql + " FORMAT JSON")).get("data", [])

    def one(self, sql):
        values = self.rows(sql)
        return values[0] if values else None

    def execute(self, sql):
        self.query(sql)
