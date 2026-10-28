# MCP-сервер базы знаний УНФ 3.0 — установка и запуск

Фаза 1: сервер отдаёт **только поиск** по карточкам. Генерацию ответа делает
тот, кто вызвал инструмент — BDS в браузере, другой агент или человек.

Сервер написан под **MCP Python SDK v2** (`mcp>=2.0`). В v2 класс `FastMCP`
переименован в `MCPServer`, импорт — `from mcp.server import MCPServer`,
`host`/`port` передаются в `mcp.run()`, а проверка `Origin` настраивается
через `TransportSecuritySettings`.

## Установка

Из корня репозитория, в активированном `.venv`:

```bat
.venv\Scripts\activate
py -m pip install -r tools\requirements-mcp.txt
```

Первый запуск скачает модель `intfloat/multilingual-e5-large` (~2 ГБ) — разово.

## Запуск

```
py tools\mcp_server.py
```

Ожидаемый вывод:

```
[mcp_server] каталог карточек: ...\kb\unf30
[mcp_server] карточек в индексе: 34
[mcp_server] транспорт: streamable-http, http://127.0.0.1:8000/mcp
[mcp_server] разрешённые Origin: ['https://chat.deepseek.com', 'chrome-extension://*']
```

Параметры:

| Ключ ↕▾ | По умолчанию ↕▾ | Что задаёт ↕▾ |
|---|---|---|
| −`--port` | `8000` | порт HTTP-сервера |
| `--host` | `127.0.0.1` | интерфейс |
| `--kb` | автоопределение | путь к `kb/unf30` |
| `--stdio` | выкл. | stdio-транспорт |
| `--no-dns-protection` | выкл. | отключить проверку Origin (локальная отладка) |
⚙

Переменные окружения: `KB_PATH`, `MCP_HOST`, `MCP_PORT`, `MCP_ALLOWED_ORIGINS`.

## Ошибка 403 Invalid Origin header

Если BDS при подключении пишет `403: Invalid Origin header`, это сработала
встроенная DNS-rebinding защита. По умолчанию сервер разрешает только
`http://localhost:*` и `http://127.0.0.1:*`, а браузер отправляет свой
`Origin` (`https://chat.deepseek.com` или `chrome-extension://...`).

**Решение 1 (штатное).** Сервер уже добавляет нужные Origin в allowlist.
Перезапустите его и нажмите «Получить инструменты» в BDS снова.

**Решение 2 (если Origin другой).** Узнать фактический Origin можно в логе
сервера — при 403 там будет строка `Invalid Origin header: <значение>`.
Добавить его:

```
set MCP_ALLOWED_ORIGINS=https://chat.deepseek.com,chrome-extension://*,https://your.origin
py tools\mcp_server.py
```

**Решение 3 (крайнее, только локально).** Отключить защиту:

```
py tools\mcp_server.py --no-dns-protection
```

Это допустимо, пока сервер слушает `127.0.0.1` и не выставлен в сеть.

## Проверка до подключения к BDS

```
py tools\check_mcp.py "как настроить ордерный склад"
```

Скрипт делает рукопожатие, печатает список инструментов и результат поиска.

## Подключение к BDS

1. Настройки MCP-серверов в BDS → добавить сервер.
2. Имя: `unf30-kb`. URL: `http://127.0.0.1:8000/mcp`.
3. Транспорт: **streamable HTTP**.
4. Сохранить → «Получить инструменты». Должны появиться `search_kb`,
`get_card`, `kb_stats`.

## Инструменты сервера

| Инструмент ↕▾ | Что делает ↕▾ |
|---|---|
| −`search_kb(query, top_k, type, status, level)` | top-N карточек по семантическому сходству |
| `get_card(card_id)` | полный текст карточки по id |
| `kb_stats()` | состав базы |
⚙

## Кэш

Векторы лежат в `ai_workspace/.cache/passages_e5_*.npz`. При изменении
карточки кэш инвалидируется (ключ — хэш текстов) и пересчитывается при
следующем запуске: 34 карточки — несколько секунд.

## Что дальше (фаза 2)

1. `ask_kb(query)` — retrieval + вызов DeepSeek API + готовый ответ.
2. `DEEPSEEK_API_KEY` в `.env`, `.env` в `.gitignore`, в репозитории — `.env.example`.
3. Замер: токены, стоимость, качество на 19 тестовых вопросах.

