import threading
from datetime import datetime, timedelta

from errors import NotFound


def next_timestamp(last=None):
    now = datetime.now().replace(microsecond=0)
    if last:
        now = max(now, datetime.fromisoformat(last) + timedelta(seconds=1))
    return now.strftime("%Y-%m-%d %H:%M:%S")


class EnergosbytService:
    def __init__(self, repositories):
        self.repos = repositories
        self.lock = threading.RLock()

    def get_user(self, user_id):
        row = self.repos.users.get(user_id)
        if row is None:
            raise NotFound()
        return {key: row[key] for key in ("id", "fio", "phone", "phone_prev")}

    def update_user(self, user_id, changes):
        with self.lock:
            current = self.repos.users.get(user_id)
            if current is None:
                raise NotFound()
            fio = changes.get("fio", current["fio"])
            phone = changes.get("phone", current["phone"])
            previous = current["phone"] if phone != current["phone"] else current["phone_prev"]
            self.repos.users.save(
                user_id, fio, phone, previous, current["created_at"],
                next_timestamp(current["updated_at"]),
            )

    def get_realty(self, realty_id):
        row = self.repos.realty.get(realty_id)
        if row is None:
            raise NotFound()
        return row

    def list_readings(self, realty_id, date_from, date_to):
        self.get_realty(realty_id)
        readings = self.repos.readings.list_for_realty(realty_id, date_from, date_to)
        return {"readings": readings, "count": len(readings)}

    def create_reading(self, realty_id, reading):
        if not all((
            self.repos.realty.exists(realty_id),
            self.repos.users.exists(reading["user_id"]),
            self.repos.gauges.exists(reading["gauge_id"]),
            self.repos.tariffs.exists(reading["tariff_id"]),
        )):
            raise NotFound()
        with self.lock:
            last = self.repos.readings.latest_stamp(realty_id, reading["reading_date"])
            self.repos.readings.save(realty_id, reading, next_timestamp(last))

    def list_invoices(self, realty_id, limit, offset):
        self.get_realty(realty_id)
        count = self.repos.invoices.count_for_realty(realty_id)
        invoices = self.repos.invoices.list_for_realty(realty_id, limit, offset)
        return {"invoices": invoices, "count": count}

    def get_tariff(self, day):
        row = self.repos.tariffs.active_on(day)
        if row is None:
            raise NotFound()
        return row

    def install_gauge(self, realty_id, gauge_id):
        if not self.repos.realty.exists(realty_id) or not self.repos.gauges.exists(gauge_id):
            raise NotFound()
        with self.lock:
            active = self.repos.bindings.active_for_realty(realty_id)
            version = self.repos.bindings.next_version(realty_id)
            if active:
                self.repos.bindings.cancel(realty_id, active)
            self.repos.bindings.install(realty_id, gauge_id, next_timestamp(), version)
