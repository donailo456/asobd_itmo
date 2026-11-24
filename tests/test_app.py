import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from http_api import Handler
from service import EnergosbytService


class UsersFake:
    def __init__(self):
        self.row = {
            "id": 1,
            "fio": "Иванов Иван",
            "phone": "+79000000001",
            "phone_prev": "",
            "created_at": "2023-11-01 00:00:00",
            "updated_at": "2023-11-01 00:00:00",
        }

    def get(self, user_id):
        return self.row.copy() if user_id == 1 else None

    def save(self, user_id, fio, phone, phone_prev, created_at, updated_at):
        self.row.update(fio=fio, phone=phone, phone_prev=phone_prev,
                        created_at=created_at, updated_at=updated_at)


class BindingsFake:
    def __init__(self):
        self.active = {"gauge_id": 1, "created_at": "2023-11-01 00:00:00", "version": 1}
        self.cancelled = None
        self.installed = None

    def active_for_realty(self, realty_id):
        return self.active

    def next_version(self, realty_id):
        return 2

    def cancel(self, realty_id, active):
        self.cancelled = (realty_id, active)

    def install(self, realty_id, gauge_id, created_at, version):
        self.installed = (realty_id, gauge_id, version)


class ServiceTests(unittest.TestCase):
    def test_user_name_and_previous_phone(self):
        users = UsersFake()
        service = EnergosbytService(SimpleNamespace(users=users))
        service.update_user(1, {"fio": "Петров Пётр", "phone": "+79111111111"})
        service.update_user(1, {"phone": "+79222222222"})
        self.assertEqual(service.get_user(1), {
            "id": 1,
            "fio": "Петров Пётр",
            "phone": "+79222222222",
            "phone_prev": "+79111111111",
        })

    def test_gauge_replacement_cancels_previous_version(self):
        bindings = BindingsFake()
        repos = SimpleNamespace(
            realty=SimpleNamespace(exists=lambda realty_id: True),
            gauges=SimpleNamespace(exists=lambda gauge_id: True),
            bindings=bindings,
        )
        EnergosbytService(repos).install_gauge(1, 2)
        self.assertEqual(bindings.cancelled[1]["version"], 1)
        self.assertEqual(bindings.installed, (1, 2, 2))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer

        Handler.service = SimpleNamespace(
            get_user=lambda user_id: {"id": user_id, "fio": "Иванов", "phone": "+7900", "phone_prev": ""},
            list_readings=lambda realty_id, date_from, date_to: {"readings": [], "count": 0},
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        payload = None if body is None else json.dumps(body)
        connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_routes_and_validation(self):
        self.assertEqual(self.request("GET", "/ping"), (200, b""))
        status, body = self.request("GET", "/users/1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], 1)
        status, body = self.request("GET", "/realty/1/readings?date_from=bad&date_to=2026-10-01")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {"message": 'invalid "date_from" parameter'})


if __name__ == "__main__":
    unittest.main()
