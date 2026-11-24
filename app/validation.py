import re
from datetime import date

from errors import BadRequest


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


def field(body, name, test):
    value = body.get(name)
    if not test(value):
        raise BadRequest(f'invalid "{name}" field')
    return value


def parameter(params, name, default=None, kind="date"):
    value = params.get(name, [default])[0]
    if kind == "date":
        good = valid_date(value)
    else:
        good = isinstance(value, str) and bool(re.fullmatch(r"\d+", value)) and int(value) < 2**63
    if not good:
        raise BadRequest(f'invalid "{name}" parameter')
    return value if kind == "date" else int(value)


def user_changes(body):
    if not body or any(name not in ("fio", "phone") for name in body):
        raise BadRequest('invalid "fio" field')
    for name in body:
        field(body, name, lambda value: isinstance(value, str) and bool(value.strip()))
    return body


def reading(body):
    return {
        "user_id": field(body, "user_id", valid_id),
        "gauge_id": field(body, "gauge_id", valid_id),
        "tariff_id": field(body, "tariff_id", valid_id),
        "reading_date": field(body, "reading_date", valid_date),
        "day_kw": field(body, "day_kw", valid_uint),
        "night_kw": field(body, "night_kw", valid_uint),
    }
