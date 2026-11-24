import os
from http.server import ThreadingHTTPServer

from clickhouse import ClickHouseClient
from http_api import Handler
from repositories import Repositories
from service import EnergosbytService


def main():
    Handler.service = EnergosbytService(Repositories(ClickHouseClient()))
    port = int(os.getenv("APP_PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
