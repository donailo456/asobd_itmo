from clickhouse import literal


class UsersRepository:
    def __init__(self, db):
        self.db = db

    def get(self, user_id):
        return self.db.one(
            f"SELECT * FROM dim_users FINAL WHERE id={user_id} LIMIT 1"
        )

    def exists(self, user_id):
        return self.get(user_id) is not None

    def save(self, user_id, fio, phone, phone_prev, created_at, updated_at):
        self.db.execute(
            "INSERT INTO dim_users (id,fio,phone,phone_prev,created_at,updated_at) VALUES ("
            f"{user_id},{literal(fio)},{literal(phone)},{literal(phone_prev)},"
            f"{literal(created_at)},{literal(updated_at)})"
        )


class RealtyRepository:
    def __init__(self, db):
        self.db = db

    def get(self, realty_id):
        return self.db.one(
            "SELECT id,address,square,type,number,rooms,floor,porch "
            f"FROM dim_realty WHERE id={realty_id} LIMIT 1"
        )

    def exists(self, realty_id):
        return self.get(realty_id) is not None


class TariffsRepository:
    def __init__(self, db):
        self.db = db

    def exists(self, tariff_id):
        return self.db.one(
            f"SELECT id FROM dim_tariffs FINAL WHERE id={tariff_id} LIMIT 1"
        ) is not None

    def active_on(self, day):
        timestamp = literal(day + " 00:00:00")
        return self.db.one(
            "SELECT id,name,price_day_kwph,price_night_kwph,valid_from,valid_to "
            "FROM dim_tariffs FINAL "
            f"WHERE valid_from <= {timestamp} AND valid_to > {timestamp} "
            "ORDER BY valid_from DESC LIMIT 1"
        )


class GaugesRepository:
    def __init__(self, db):
        self.db = db

    def exists(self, gauge_id):
        return self.db.one(
            f"SELECT id FROM dim_gauges WHERE id={gauge_id} LIMIT 1"
        ) is not None


class ReadingsRepository:
    def __init__(self, db):
        self.db = db

    def list_for_realty(self, realty_id, date_from, date_to):
        return self.db.rows(
            "SELECT reading_date,user_id,tariff_id,gauge_id,day_kw,night_kw "
            f"FROM fact_meter_readings FINAL WHERE realty_id={realty_id} "
            f"AND reading_date BETWEEN {literal(date_from)} AND {literal(date_to)} "
            "ORDER BY reading_date"
        )

    def latest_stamp(self, realty_id, reading_date):
        row = self.db.one(
            "SELECT max(created_at) AS stamp FROM fact_meter_readings "
            f"WHERE realty_id={realty_id} AND reading_date={literal(reading_date)}"
        )
        return row["stamp"] if row else None

    def save(self, realty_id, reading, created_at):
        self.db.execute(
            "INSERT INTO fact_meter_readings "
            "(realty_id,user_id,tariff_id,gauge_id,reading_date,day_kw,night_kw,created_at) VALUES "
            f"({realty_id},{reading['user_id']},{reading['tariff_id']},{reading['gauge_id']},"
            f"{literal(reading['reading_date'])},{reading['day_kw']},{reading['night_kw']},"
            f"{literal(created_at)})"
        )


class InvoicesRepository:
    def __init__(self, db):
        self.db = db

    def count_for_realty(self, realty_id):
        return self.db.one(
            f"SELECT count() AS count FROM fact_invoice WHERE realty_id={realty_id}"
        )["count"]

    def list_for_realty(self, realty_id, limit, offset):
        return self.db.rows(
            "SELECT tariff_id,gauge_id,day_kw,night_kw,price,deadline,created_at "
            f"FROM fact_invoice WHERE realty_id={realty_id} "
            f"ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
        )


class BindingsRepository:
    def __init__(self, db):
        self.db = db

    def active_for_realty(self, realty_id):
        return self.db.one(
            "SELECT gauge_id,created_at,version FROM fact_gauge_bindings FINAL "
            f"WHERE realty_id={realty_id} AND sign=1 ORDER BY version DESC LIMIT 1"
        )

    def next_version(self, realty_id):
        row = self.db.one(
            f"SELECT max(version) AS version FROM fact_gauge_bindings WHERE realty_id={realty_id}"
        )
        return int(row["version"] or 0) + 1

    def cancel(self, realty_id, active):
        self.db.execute(
            "INSERT INTO fact_gauge_bindings VALUES "
            f"({active['gauge_id']},{realty_id},{literal(active['created_at'])},-1,{active['version']})"
        )

    def install(self, realty_id, gauge_id, created_at, version):
        self.db.execute(
            "INSERT INTO fact_gauge_bindings VALUES "
            f"({gauge_id},{realty_id},{literal(created_at)},1,{version})"
        )


class Repositories:
    def __init__(self, db):
        self.users = UsersRepository(db)
        self.realty = RealtyRepository(db)
        self.tariffs = TariffsRepository(db)
        self.gauges = GaugesRepository(db)
        self.readings = ReadingsRepository(db)
        self.invoices = InvoicesRepository(db)
        self.bindings = BindingsRepository(db)
