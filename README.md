# AV.BY Market Pulse

Интерактивный дашборд рынка подержанных автомобилей Беларуси: **реальный парсинг `cars.av.by` → аналитика на Python → графики в браузере**.

Проект собран как демонстрация навыков: сбор данных, парсинг серверного JSON, чистые агрегации, REST API, фронтенд без сборщика и тесты.

---

## Что умеет

- **Парсит `cars.av.by`** без headless-браузера: данные лежат в `__NEXT_DATA__`, 25 объявлений на страницу.
- **≈1 250 реальных автомобилей** в приложенном датасете (`data/cars.json`), 65 марок.
- **KPI-панель**: объём выборки, средняя и медианная цена, средний год, пробег, доля электромобилей.
- **9 интерактивных графиков** (ECharts):
  - распределение цен и ценовые сегменты;
  - средняя цена по маркам;
  - структура кузовов;
  - цена по годам + объём предложения;
  - типы двигателей;
  - цена против пробега (scatter);
  - сколько дней авто висит в продаже;
  - география предложения.
- **Фильтры в реальном времени**: марка → модель (каскадом), кузов, двигатель, год, цена, пробег, поиск по модели, сортировка.
- **Блок «ниже медианы по марке и модели»** — *все* такие объявления (не топ-8), с постраничной навигацией и выгрузкой в CSV. Прозрачная эвристика, а не оценка стоимости. Без выбранной модели цена сравнивается с медианой марки; если в фильтре выбрана модель, блок переключается на медиану пары **марка + модель** (нужно минимум 3 объявления, иначе блок честно сообщает, что медиану не из чего считать). Медиана всегда считается по **всему датасету**, поэтому фильтры не могут «поднять» её и впустить в блок объявление с ценой выше реальной медианы; на карточке подписано, с чем идёт сравнение. Порядок по умолчанию — самая большая разница с медианой; при выборе сортировки в фильтрах блок переупорядочивается так же, как таблица объявлений.
- **Скоринг объявлений 0–10**: до 5 баллов за более свежий год + до 5 за меньший пробег (линейная шкала по всему датасету, поэтому балл не меняется при смене фильтров). Балл показан в таблице и в карточках блока «ниже медианы», сортировки «В порядке убывания скорингового балла» и «В порядке убывания скорингового балла и возрастания цены» (балл — главный ключ, цена — вторичный, обе действуют и на таблицу, и на блок «ниже медианы»).
- **Таблица объявлений** с фото, пагинацией и ссылками на оригинал.
- **Экспорт CSV** текущей выборки (разделитель `;`, UTF-8 BOM — корректно открывается в Excel).
- **Ручное обновление данных**: один прогон скрапера обновляет срез, а открытая вкладка подхватывает его без перезагрузки (`/api/meta` или `data/meta.json` раз в 60 с + уведомление). Расписания нет намеренно: `cars.av.by` отвечает нестандартным **468** на запросы с IP-адресов GitHub Actions, поэтому свежие данные снимаются с обычного подключения, а не из облака.
- **Работает офлайн**: датасет и ECharts лежат в репозитории, сборка Node.js не нужна.

## Быстрый старт

Нужен только Python 3.11+ (проверено на 3.13). В Windows используйте лаунчер `py`.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# (опционально) обновить данные с сайта — 50 страниц ≈ 1250 авто
.\.venv\Scripts\python.exe -m scraper.cli --pages 50

# запустить дашборд
.\.venv\Scripts\python.exe -m uvicorn app.server:app --reload --port 8000
```

Откройте **http://127.0.0.1:8000**.

Датасет уже собран и лежит в `data/cars.json`, поэтому шаг со скрапингом можно пропустить.

## Обновление данных

Автоматического расписания нет: `cars.av.by` отвечает нестандартным **468** на запросы с IP-адресов GitHub Actions, поэтому облачный раннер не может снять свежий срез. Данные обновляются, когда скрапинг запускают вручную с обычного подключения.

```powershell
# свежий срез (50 страниц ≈ 1250 авто)
.\.venv\Scripts\python.exe -m scraper.cli --pages 50

# пересобрать статическую сборку для GitHub Pages
.\.venv\Scripts\python.exe scripts\build-static.py
```

Без терминала: **двойной клик по `refresh-data.bat`** — он делает оба шага и в конце открывает папку `data` с готовым файлом для загрузки. Число страниц можно передать аргументом: `refresh-data.bat 80`.

Открытая вкладка подхватывает новый срез без перезагрузки: `app/static/app.js` раз в 60 с сверяет `scraped_at` (`/api/meta` в API-режиме, `data/meta.json` на Pages) и показывает уведомление.

По желанию то же самое можно повесить на Windows Task Scheduler — задача сработает, только если компьютер включён:

```powershell
# зарегистрировать задачу «AVBY-MarketPulse-Daily» (каждый день в 13:00)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-schedule.ps1

# другое время / больше страниц
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -Time 09:30 -Pages 80

# обновить данные прямо сейчас, не дожидаясь 13:00
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\update-dashboard.ps1

# убрать задачу
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\unregister-schedule.ps1
```

Что происходит:

| Компонент | Роль |
| --- | --- |
| `scripts/register-schedule.ps1` | создаёт задачу планировщика на текущего пользователя, `StartWhenAvailable` (догоняет пропущенный запуск после сна) |
| `scripts/update-dashboard.ps1` | запускает скрапер, пишет лог, хранит последние 30 логов, не даёт запускам пересекаться (mutex); с ключом `-Build` ещё и пересобирает `docs/` |
| `scraper/cli.py` | пишет датасет атомарно (`cars.json.tmp` → `os.replace`), поэтому сбойный запуск не портит `data/cars.json` |
| `app/static/app.js` | раз в 60 с проверяет `/api/meta`; при новом `scraped_at` перерисовывает дашборд и показывает уведомление |

Проверка:

```powershell
Get-ScheduledTask -TaskName AVBY-MarketPulse-Daily | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName AVBY-MarketPulse-Daily   # NextRunTime
Get-Content logs\update-$(Get-Date -Format 'yyyy-MM-dd').log -Tail 20 -Encoding UTF8
```

Логи: `logs\update-YYYY-MM-DD.log` (в `.gitignore`). Задача работает, пока пользователь вошёл в систему; сервер `uvicorn` при этом должен быть запущен, чтобы страница отдавала свежие данные.

## Публикация без своего компьютера (GitHub Pages)

GitHub Pages раздаёт статическую сборку из `docs/`, поэтому демо открывается без Python и без вашего ПК. Данные при этом статичны: свежий срез попадает на сайт после ручного скрапинга и загрузки `data/cars.json` + `docs/` в репозиторий.

```powershell
# собрать docs/ из app/static + data/cars.json
.\.venv\Scripts\python.exe scripts\build-static.py

# проверить сборку локально (без FastAPI)
py -m http.server 8001 --directory docs
```

`scripts/build-static.py` копирует `app/static` → `docs/`, кладёт рядом `data/cars.json` и `data/meta.json`, добавляет `.nojekyll` и помечает `index.html` атрибутом `data-mode="static"`. В этом режиме аналитика считается прямо в браузере (`app/static/analytics.js` — JS-порт `app/analytics.py`), а CSV собирается на клиенте.

| Режим | Когда включается | Что считает данные |
| --- | --- | --- |
| `api` | страница отдана FastAPI (`/api/meta` отвечает) | `app/analytics.py` на сервере |
| `static` | страница собрана скриптом (`data-mode="static"`) | `app/static/analytics.js` в браузере |

Workflow `.github/workflows/update-dashboard.yml` (ручной режим, без расписания):

- запускается вручную (`workflow_dispatch`) и любым push в `main`, кроме коммитов только в `docs/` — то есть загрузка свежего `data/cars.json` сама пересобирает сайт. Зацикливания нет: коммиты встроенного `GITHUB_TOKEN` workflows не триггерят;
- шаги: установка зависимостей → `pytest` → `build-static.py` → коммит `data/cars.json` и `docs/`;
- скрапинг в облаке вынесен в отдельный необязательный шаг с `continue-on-error` и включается галочкой `scrape` при ручном запуске: `cars.av.by` отдаёт нестандартный **468** клиентам с IP-адресов GitHub, поэтому срез снимается локально; если блокировку когда-нибудь снимут, шаг начнёт работать сам;
- `scraper/avby.py` на 468 повторяет запрос через `curl` (другой TLS/HTTP-фингерпринт), `scripts/probe-avby.py` печатает вердикт по обоим транспортам.

Как обновить опубликованные данные вручную:

1. `.\.venv\Scripts\python.exe -m scraper.cli --pages 50` (или `scripts\update-dashboard.ps1 -Build` — скрапинг + пересборка `docs/` + лог);
2. загрузить `data/cars.json` в репозиторий — workflow сам пересоберёт `docs/` и опубликует сайт.

Как включить:

1. Создать репозиторий на GitHub и запушить проект (`git` или GitHub Desktop).
2. **Settings → Pages → Source: Deploy from a branch → Branch `main`, папка `/docs`**.
3. **Actions → Refresh dashboard → Run workflow** — первый прогон вручную, чтобы проверить права и сборку.

### Если git не установлен: публикация через браузер

Всё то же самое можно сделать на github.com, без командной строки. Репозиторий должен быть **публичным** — на бесплатном плане Pages работает только для публичных репозиториев, а для портфолио это и нужно.

1. **New repository** → имя, `Public`, без README/лицензии.
2. **Add file → Upload files** → перетащите папки `app`, `data`, `docs`, `scraper`, `scripts`, `tests` и файлы `README.md`, `AGENTS.md`, `requirements.txt`, `pyproject.toml`, `.gitignore` → **Commit changes**.
   Не загружайте `.venv`, `logs`, `__pycache__`, `.pytest_cache` (это локальный мусор, он в `.gitignore`).
3. Скрытые файлы и папки drag & drop обычно пропускает — создайте их вручную через **Add file → Create new file**:
   - `.github/workflows/update-dashboard.yml` — вставьте содержимое одноимённого файла из проекта;
   - `docs/.nojekyll` — пустой файл (можно с одним переводом строки).
4. **Settings → Pages** → Source: `Deploy from a branch`, Branch: `main`, папка `/docs`.
5. Первый прогон стартует сам: коммит workflow-файла — это push в `main`, а в workflow есть триггер `push`. Если кнопка **Actions → Refresh dashboard → Run workflow** выдаёт «An unexpected error has occurred», просто сделайте любой коммит в `main` — прогон запустится от него.

Ограничения веб-загрузки, которые нас не задевают: до 100 файлов за раз и до 25 МБ на файл — у проекта 35 файлов и максимум 1 МБ (`echarts.min.js`).

Если файлов много и не хочется возиться со скрытыми, проще поставить **GitHub Desktop**: он добавляет папку целиком, учитывает `.gitignore` и делает push одной кнопкой.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pytest
# один файл / один тест
.\.venv\Scripts\python.exe -m pytest tests/test_analytics.py
.\.venv\Scripts\python.exe -m pytest tests/test_api.py::test_dashboard_brand_filter_narrows_results
```

Тесты не ходят в сеть: парсер проверяется на синтетическом `__NEXT_DATA__`, API — через `TestClient` на локальном датасете, сборка Pages — во временном каталоге.

## Архитектура

```
cars.av.by
    │  HTML с <script id="__NEXT_DATA__">
    ▼
scraper/avby.py     fetch + retry + parse → dataclass Car
    │
    ▼
data/cars.json      снапшот рынка (коммитится)
    │
    ├─────────────────────────────┐
    ▼                             ▼
app/store.py        загрузка   scripts/build-static.py → docs/ (GitHub Pages)
app/analytics.py    агрегации  app/static/analytics.js (тот же расчёт в браузере)
    │
    ▼
app/server.py       FastAPI: /api/dashboard, /api/filters, /api/export.csv
    │
    ▼
app/static/         index.html + styles.css + app.js + analytics.js + vendor/echarts.min.js
```

| Путь | Ответственность |
| --- | --- |
| `scraper/avby.py` | загрузка страниц, парсинг `__NEXT_DATA__`, нормализация полей |
| `scraper/cli.py` | CLI-обёртка, прогресс, запись `data/cars.json` |
| `app/analytics.py` | фильтрация, KPI, гистограммы, агрегаты, «лучшие предложения» — эталонная реализация |
| `app/store.py` | чтение датасета с автоперезагрузкой при изменении файла |
| `app/server.py` | REST API, CSV-экспорт, раздача статики |
| `app/static/` | дашборд без сборщика; ECharts подключён локально |
| `app/static/analytics.js` | JS-порт `app/analytics.py` для статического режима |
| `scripts/build-static.py` | сборка `docs/` для GitHub Pages (датасет + метаданные + `.nojekyll`) |
| `scripts/` | PowerShell-обвязка: обновление данных, регистрация/снятие задачи на 13:00 |
| `docs/` | опубликованный статический сайт (генерируется, коммитится) |
| `.github/workflows/update-dashboard.yml` | ежедневный ETL в облаке: тесты → скрапинг → сборка → коммит |

## API

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| `GET` | `/api/dashboard` | KPI, все графики, первая страница «ниже медианы» и страница объявлений |
| `GET` | `/api/deals` | все объявления ниже медианы своей марки, постранично |
| `GET` | `/api/deals.csv` | CSV со всеми объявлениями ниже медианы (не только текущая страница) |
| `GET` | `/api/filters` | доступные марки, кузова, двигатели и диапазоны |
| `GET` | `/api/meta` | источник, дата среза, размер датасета |
| `GET` | `/api/export.csv` | CSV текущей выборки |
| `GET` | `/health` | health-check |

Параметры `/api/dashboard`, `/api/deals`, `/api/deals.csv` и `/api/export.csv`: `brand`, `body`, `fuel`, `year_min`, `year_max`, `price_min`, `price_max`, `mileage_max`, `q`, `sort`, `page`, `page_size`.

## Как устроен парсинг

`cars.av.by` — Next.js-приложение. Каждая страница фильтра отдаёт готовый HTML, внутри которого лежит JSON:

```
props.initialState.filter.main.adverts
```

Оттуда берутся `price.usd.amount`, `price.byn.amount`, `properties[]`, `metadata`, `photos`, `publicUrl` и т. д. Пагинация — `?page=N`, по 25 объявлений.

Особенности, которые учтены в коде:

- повторы промо-объявлений между страницами → дедупликация по `id`;
- `engine_capacity` приходит с запятой (`"2,0"`) → нормализуется в `2.0`;
- сеть нестабильна → 3 попытки с backoff и пауза между страницами;
- в Windows консоль в cp1251, поэтому кириллица в выводе может выглядеть «кракозябрами» — файлы при этом корректный UTF-8.

## Стек

Python 3.13 · FastAPI · Uvicorn · ECharts 5 · ванильный JS/CSS · pytest. Без Node.js, без сборки фронтенда, без ORM и БД.

## Дисклеймер

Учебный демо-проект. Не аффилирован с `av.by`. Данные получены из публично доступных страниц с щадящей задержкой между запросами и используются только для аналитики. Не публикуйте датасет как собственный продукт и уважайте правила сайта.
