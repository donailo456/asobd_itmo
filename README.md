# Лабораторная работа №1 — SCD в ClickHouse

Проект запускается из корня репозитория. Нужны Docker Compose, Make и Python 3 без внешних пакетов.

```sh
make run
make setup
curl -i localhost:8080/ping
make teardown
make stop
```

`make setup` создаёт семь таблиц, генерирует CSV в `data/` и загружает данные.
`make load` очищает все семь таблиц перед загрузкой: повторный вызов не создаёт дубли даже в `MergeTree`.
`make teardown` удаляет базу `energosbyt`; следующий `make setup` создаст её заново.
Настройки портов и подключения — в `.env.local`. `data/` и `volume/` исключены из Git. Файл `.labrc` содержит `LAB=1`. Примеры запросов для Postman — в `api/`.

## Схема и ключи

Факт показаний партиционирован по месяцу даты показания, ключ `(realty_id, reading_date)` позволяет `ReplacingMergeTree(created_at)` выбрать последнюю корректировку дня. Факт счетов партиционирован по месяцу выставления, сортирован по `(realty_id, created_at)` для списка счетов объекта. Тарифы имеют ключ `(id, valid_from)`, чтобы версии одного тарифа за разные интервалы сохранялись. Собственники имеют ключ `id`, чтобы новое ФИО и телефон заменяли текущую версию. Установки счётчиков имеют ключ `(realty_id, gauge_id, version)`: аннулирование с тем же ключом, версией и `created_at` схлопывается с установкой. Недвижимость и счётчики отсортированы по `id`, их партиция группирует до 1000 идентификаторов.

Данные включают 1000 объектов в 10 домах, 1100 счётчиков, 1000 собственников, 3 версии тарифа, 100 замен счётчика, ежедневные показания с 2023-11-01 по 2026-10-31, около 3% корректировок и 36 000 счетов. Каждый счёт сохраняет цену версии тарифа на месяц выставления.

## Ручная проверка сценариев

Примеры ниже выполняются после `make setup`; запросы к ClickHouse выполняются через `docker compose --env-file .env.local exec -T clickhouse clickhouse-client --query 'SQL'`.

| Сценарий | HTTP-действие и SQL-проверка | Что видно |
| --- | --- | --- |
| SCD 1 | `PATCH /users/1` с `{"fio":"Петров Пётр Петрович"}`; `SELECT fio FROM energosbyt.dim_users FINAL WHERE id=1` | Текущее ФИО новое; в логической версии `FINAL` старого нет. |
| SCD 3 | Дважды `PATCH /users/1` с разными `phone`; `SELECT phone,phone_prev FROM energosbyt.dim_users FINAL WHERE id=1` | Последний и предпоследний телефон. |
| SCD 2 | `GET /tariffs?date=2025-10-31` и `GET /tariffs?date=2025-11-01`; `SELECT valid_from,valid_to,price_day_kwph FROM energosbyt.dim_tariffs FINAL ORDER BY valid_from` | Цены 500 и 570 копеек, интервалы не пересекаются. |
| Старый счёт | `SELECT price,created_at FROM energosbyt.fact_invoice WHERE realty_id=1 ORDER BY created_at LIMIT 1`; сравнить с тарифом на месяц счёта | Сумма сохранена по исторической цене. |
| Корректировка | `POST /realty/1/readings` с датой из периода; `SELECT reading_date,day_kw FROM energosbyt.fact_meter_readings FINAL WHERE realty_id=1 AND reading_date='2026-10-01'` | Одна, последняя версия показания. |
| Замена счётчика | `POST /realty/1/gauges` с `{"gauge_id":2}`; `SELECT gauge_id,sign,version FROM energosbyt.fact_gauge_bindings FINAL WHERE realty_id=1` | Прежняя активная установка аннулирована, новая имеет увеличенную версию. |
| Удаление ошибки | `INSERT INTO energosbyt.dim_gauges VALUES (999999,'Ошибка','',now())`; `ALTER TABLE energosbyt.dim_gauges DELETE WHERE id=999999`; `SELECT count() FROM energosbyt.dim_gauges WHERE id=999999` | После завершения мутации ошибочная строка удалена. |

Для удаления можно дождаться мутации запросом `SELECT is_done FROM system.mutations WHERE database='energosbyt' AND table='dim_gauges' ORDER BY create_time DESC LIMIT 1`. В этой лабораторной правка собственника через `ReplacingMergeTree` оставляет физическую старую строку до фонового слияния; `FINAL` показывает текущее логическое состояние.

## API

`GET /ping`, `GET/PATCH /users/{id}`, `GET /realty/{id}`, `POST/GET /realty/{id}/readings`, `GET /realty/{id}/invoices`, `GET /tariffs?date=YYYY-MM-DD`, `POST /realty/{id}/gauges`. Тела запросов и ответы — JSON; ошибки имеют поле `message`. API не использует авторизацию согласно заданию.

## Проверка в GitHub Actions

Файлы запуска находятся в корне репозитория. Номер работы задан в `.labrc`; проверяющий workflow лежит в `.github/workflows/lab1.yml` и запускается при открытии Pull Request.
