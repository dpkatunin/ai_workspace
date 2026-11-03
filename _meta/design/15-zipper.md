# 15-zipper.md — Распаковка ZIP: диагностика и надёжный скрипт

**Дата:** 2026-11-03 (обновлено: правило формирования путей в ZIP)
**Статус:** принят
**Основание:** файлы «последнее время не ложатся как надо, приходится делать руками». Разбор причин и замена распаковщика.

**⚠️ ВАЖНО. Два уровня путей:**
1. **Распаковщик универсальный:** `$targetDir = "C:\ai_workSpaceGitHub"`. Он распаковывает всё в корень рабочей папки. Скрипт не меняется под конкретный проект.
2. **Агент формирует ZIP с префиксом репозитория:**
   - публичный репозиторий: `ai_workspace/_meta/design/...`
   - приватный репозиторий: `ai_workspace_projects/...`
   
   **Если агент упакует файлы без префикса (`_meta/...`), они лягут в корень `C:\ai_workSpaceGitHub` мимо репозитория.** Это главная причина «файлы не ложатся как надо».

---

## 1. Что ломается

### 1.1. Застревание на битом ZIP (старый батник)

Старый фрагмент:
```bat
powershell -Command "try { Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%TARGET_DIR%' -Force; Remove-Item -Path '%ZIP_FILE%' -Force; ... } catch { ... }"
```

`Expand-Archive` и `Remove-Item` — в одном `try`. Если `Expand-Archive` упал (битый ZIP), `Remove-Item` **не выполнится**. ZIP остаётся. Следующий цикл находит **тот же** ZIP, снова падает. **Бесконечный цикл на одном битом файле.**

### 1.2. Race condition: 3 секунды вслепую

```
timeout /t 3 >nul
```

3 секунды на «завершение скачивания». Если браузер пишет дольше — `Expand-Archive` читает недописанный файл, падает.

### 1.3. Берётся не тот ZIP

```
for %%F in ("%WATCH_DIR%\*.zip") do set "ZIP_FILE=%%F"
```

Порядок итерации `for` не гарантирован как «по времени». Если в `C:\dsh-out` лежит несколько ZIP — `ZIP_FILE` будет **последним в итерации**, а не самым новым.

### 1.4. `Expand-Archive` в PowerShell 5.1 хрупок

- Плохо работает с ZIP, где имена в UTF-8 без флага UTF-8.
- `-Force` перезаписывает файлы, но **не удаляет** те, которых больше нет в новом архиве.

### 1.5. Отсутствие префикса репозитория в путях ZIP (главная причина «мимо»)

Агент упаковывает `_meta/design/00-START-HERE-v2.md`. Распаковщик кладёт это в `C:\ai_workSpaceGitHub\_meta\...` — рядом с папкой `ai_workspace`, а не внутри неё. Файлы «не ложатся как надо», хотя распаковка прошла успешно.

**Правильно:** агент упаковывает `ai_workspace/_meta/design/00-START-HERE-v2.md`. Распаковщик кладёт это в `C:\ai_workSpaceGitHub\ai_workspace\_meta\...` — точно в репозиторий.

---

## 2. Что проверить прямо сейчас (диагностика)

1. **`C:\dsh-out`** — сколько ZIP? Если больше одного — удалите все.
2. **`C:\ai_workSpaceGitHub`** — есть ли там папка `_meta` или `kb` (рядом с `ai_workspace`)? Если да — это признак 1.5: ZIP упакован без префикса. Удалите эти папки, перегенерируйте ZIP.
3. **`C:\ai_workSpaceGitHub\ai_workspace\_meta\design\`** — есть ли там `00-START-HERE-v2.md`? Если нет — распаковка ушла мимо.
4. **Консоль батника** — если «ОШИБКА» много раз подряд, это 1.1 (битый ZIP, застревание).

---

## 3. Надёжный распаковщик (замена батника)

Ключевые изменения: стабилизация размера, выбор самого нового ZIP, `ZipFile` вместо `Expand-Archive`, валидация ZIP, лог в файл, битый ZIP → `.bad` (не застревает). **Путь распаковки универсальный:** `C:\ai_workSpaceGitHub`.

### 3.1. `unzip-watcher.ps1`

```
# unzip-watcher.ps1 — запускать в PowerShell
$watchDir  = "C:\dsh-out"
$targetDir = "C:\ai_workSpaceGitHub"
$logFile   = Join-Path $watchDir "unzip.log"

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line
    Write-Host $line
}

if (-not (Test-Path $targetDir)) {
    Write-Log "ОШИБКА: целевая папка не существует: $targetDir"
    exit 1
}

Write-Log "Старт. Жду ZIP в $watchDir → распаковка в $targetDir"

while ($true) {
    $zips = Get-ChildItem -Path $watchDir -Filter "*.zip" -File |
            Sort-Object LastWriteTime -Descending

    if ($zips.Count -eq 0) { Start-Sleep -Seconds 2; continue }

    $zip = $zips[0]
    Write-Log "Найден: $($zip.Name) ($($zip.Length) bytes, $($zip.LastWriteTime))"

    # Ждём стабилизации размера: 2 подряд одинаковых замера с интервалом 1 с
    $prevSize = -1; $stable = 0
    while ($stable -lt 2) {
        Start-Sleep -Seconds 1
        $curSize = (Get-Item $zip.FullName).Length
        if ($curSize -eq $prevSize) { $stable++ } else { $stable = 0 }
        $prevSize = $curSize
    }
    Write-Log "Размер стабилен: $prevSize bytes"

    # Валидация: читаем список entries, если не открывается — битый
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($zip.FullName)
        $entries = @($archive.Entries | ForEach-Object { $_.FullName })
        $archive.Dispose()
        Write-Log "ZIP валиден. Записей: $($entries.Count)"
        $entries | ForEach-Object { Write-Log "  -> $_" }
    } catch {
        Write-Log "ОШИБКА: ZIP невалиден: $_"
        Rename-Item $zip.FullName "$($zip.FullName).bad" -Force
        continue
    }

    # Распаковка с overwrite по каждому entry
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($zip.FullName)
        foreach ($entry in $archive.Entries) {
            if ([string]::IsNullOrEmpty($entry.Name)) { continue }  # папка
            $destPath = Join-Path $targetDir $entry.FullName
            $destDir  = Split-Path $destPath -Parent
            if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destPath, $true)
        }
        $archive.Dispose()
        Write-Log "Распаковано в $targetDir"
    } catch {
        Write-Log "ОШИБКА распаковки: $_"
        continue
    }

    try {
        Remove-Item $zip.FullName -Force
        Write-Log "ZIP удалён"
    } catch {
        Write-Log "ОШИБКА удаления: $_ (ZIP остался; следующий цикл его проигнорирует по времени)"
    }

    Start-Sleep -Seconds 2
}
```

### 3.2. Запуск

Вариант A — прямо в PowerShell:

```
powershell -ExecutionPolicy Bypass -File C:\tools\unzip-watcher.ps1
```

Вариант B — через батник `C:\tools\Запуск распаковки.bat`:

```
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0unzip-watcher.ps1"
pause
```

### 3.3. Что изменилось по сравнению с старым батником

| Было | Стало |
|---|---|
| `timeout /t 3` вслепую | Стабилизация размера (2 замера по 1 с) |
| Любой ZIP из папки | Самый новый по `LastWriteTime` |
| `Expand-Archive -Force` | `ZipFile` + `ExtractToFile(overwrite=true)` |
| Один `try` на распаковку + удаление | Разделены; битый ZIP → `.bad` |
| Нет лога | `unzip.log` рядом с ZIP |
| Не видно, что легло | Лог каждого entry |

---

## 4. Требования к формированию ZIP (со стороны агента) — ГЛАВНОЕ

**Агент ОБЯЗАН упаковывать файлы с префиксом репозитория в путях.** Это правило без исключений.

| Репозиторий | Правильный путь в ZIP | Неправильно |
|---|---|---|
| Публичный `ai_workspace` | `ai_workspace/_meta/design/00-START-HERE-v2.md` | `_meta/design/00-START-HERE-v2.md` |
| Публичный `ai_workspace` | `ai_workspace/kb/unf30/...` | `kb/unf30/...` |
| Приватный `ai_workspace_projects` | `ai_workspace_projects/...` | `...` (без префикса) |

**Дополнительно:**

- Имена файлов — только ASCII.
- Не создавать пустые папки.
- Не использовать `./`, `/` в начале, `..` в путях.
- Если файлов много — разбивать на несколько ZIP по слоям (каждый — с префиксом).

**Проверка перед отправкой:** в списке `entries` (который распаковщик пишет в лог) первая часть каждого пути — `ai_workspace/` или `ai_workspace_projects/`. Если нет — ZIP сформирован неправильно.

---

## 5. Алгоритм действий при сбое распаковки

1. Посмотреть `C:\dsh-out\unzip.log` — что за файл, сколько байт, валиден ли.
2. Если «ZIP невалиден» и переименован в `.bad` — удалить `.bad`, перегенерировать ZIP.
3. Если «Распаковано», но файлов нет в `C:\ai_workSpaceGitHub\ai_workspace` — проверить, не легли ли в `C:\ai_workSpaceGitHub` (корень). Если да — **ZIP без префикса репозитория** (см. §4). Удалить мусор, перегенерировать.
4. Если ZIP остался и не удалился — закрыть в проводнике/архиваторе, подождать 5 с.
5. Если `C:\dsh-out` пуст, а ZIP «был» — проверить, не сохраняется ли в `Downloads`.

---

## 6. Ограничения

- PowerShell 5.1 — `ZipFile` работает, но без UTF-8 флага. Для ASCII — нормально.
- Скрипт не удаляет «старые» файлы из target, которых нет в новом ZIP (`git clean -n` → проверить → `git clean -f`).
- Скрипт не делает `git commit`.
- Скрипт не проверяет, что ZIP содержит префикс репозитория. Это — на агенте (§4) и на пользователе при проверке (§5).

</BDS:create_file>
<BDS:create_file fileName="ai_workspace/_meta/design/13-chat-migration.md">

```markdown
# 13-chat-migration.md — Регламент переезда в новый чат

**Дата:** 2026-11-03 (обновлено: правило путей ZIP — префикс репозитория)
**Статус:** принят
**Основание:** переезды до сих пор не без потерь. Причины: (1) агент не читает ключевые файлы, (2) читает, но не понимает, (3) понимает, но игнорирует, (4) память модели подменяет факты, (5) ZIP не распаковался / не туда, **в т.ч. без префикса репозитория**.

---

## 1. Почему переезды теряют качество

| Причина | Пример из практики | Что делаем |
|---|---|---|
| Агент не читает START-HERE | Прогон 1 (№6): без START-HERE агент не знает про обязательный `search_config` | Стартовый промпт + контрольные вопросы |
| Агент читает, но не понимает | «Понял» без проверки — пустое слово | Контрольные вопросы, ответ письменно |
| Агент понимает, но игнорирует | Д17: знает правила, но ставит `🌐` без вызова | Внешний валидатор (§12.5) + транскрипт |
| Память модели подменяет факты | Д17: «помню, что в прогоне 7 было» — атрибуция неверна | Маркер `📝` с датой чекпоинта, не с номером прогона |
| Чекпоинт неполный | Детали теряются | Чекпоинт пишется сразу, с транскриптом |
| **ZIP не распаковался / не туда** | «Файлы не ложатся как надо» | §9 + `15-zipper.md` + `16-zipper-howto.md` |
| **ZIP без префикса репозитория** | `_meta/...` вместо `ai_workspace/_meta/...` → ложится в корень `C:\ai_workSpaceGitHub` мимо `ai_workspace` | §9.4: агент обязан упаковывать с префиксом репозитория |

---

## 2. Обязательный порядок чтения (для нового чата)

1. _meta/design/00-START-HERE-v2.md          (2 мин)
2. _meta/design/13-chat-migration.md         (этот, 3 мин)
3. _meta/checkpoints/2026-11-03-checkpoint-v2.md  (5 мин)

```

**Опционально:** `11-protocol-v2.md`, `12-architecture-v2.md`, `14-lessons-learned.md`, `15-zipper.md`, `16-zipper-howto.md`, `conventions.md`.

**Не читать без нужды:** `_raw/`, `_source/` (ADR-002), `00-START-HERE.md` (v1, архив).

---

## 3. Стартовый промпт для нового чата

```

Прочитай через read_meta_file три файла:

- _meta/design/00-START-HERE-v2.md
- _meta/design/13-chat-migration.md
- _meta/checkpoints/2026-11-03-checkpoint-v2.md

После чтения — ответь на 5 контрольных вопросов из 00-START-HERE-v2.md §8
(письменно, коротко). Не начинай работу, пока не ответишь.

Если ответ неполный — перечитай нужный раздел и ответь заново.

После контрольных вопросов — жди инструкцию. Не начинай работы по своей инициативе.

```

---

## 4. Контрольные вопросы

1. Какой слой сейчас в приоритете — данные, проверка или процесс?
2. Что делать, если `search_kb` вернул 5 карточек с релевантностью 0.79–0.82?
3. Можно ли поставить `⚙️` на имя `Document.X`, если `search_config` в этом прогоне не вызывался?
4. Для вопроса «как ввести в оборот излишки маркированного товара» — что должно быть в ответе до выбора документа?
5. Какой источник выше по весу для вопроса «есть ли в УНФ тип эмиссии „Маркировка вне производства“» — docs.crpt.ru или `read_config_file`?

**Правильные ответы:**
1. Данные (MCP v2 → CONFIG-парсер).
2. Признать «нет покрытия», перейти к WEB.
3. Нет. Только `📝` или `⚠️`.
4. Таблица состояний (диагностическое дерево).
5. `read_config_file` (CONFIG).

---

## 5. Критерии готовности к работе (после переезда)

- [ ] Ответил на все 5 контрольных вопросов.
- [ ] Не начал работу до инструкции.
- [ ] В первом ответе `/1c` есть «Вызовы в этом прогоне».
- [ ] В первом ответе `/1c` есть вызов `validate_answer` (после реализации валидатора).
- [ ] Ни один `⚙️`/`🌐`/`📗` не стоит без вызова.
- [ ] `C:\ai_workSpaceGitHub\ai_workspace` — актуальный клон, без папки `_meta` в корне `C:\ai_workSpaceGitHub`.

---

## 6. Что делать при потере качества в новом чате

1. Остановить работу.
2. Показать транскрипт: какие вызовы были, какие нет.
3. Спросить: «Какой файл ты прочитал? Ответь по §8 START-HERE-v2».
4. Если не ответил — вернуться к стартовому промпту.
5. Если нарушает — Д17/Д19. До валидатора — явное «нет вывода — нет маркера».

**Антипаттерн:** «Продолжай, я тебе доверяю».

---

## 7. Обновление чекпоинта

**Правило:** чекпоинт пишется сразу после прогона.

**Что должно быть:** дата, статус, очередь вопросов, таблица прогонов, подтверждено через CONFIG, детали значимых прогонов, дефекты Д1–Д19, решения, следующий шаг (справка, не команда).

**Чего не должно быть:** «потом допишу», ссылки на «как обсуждали выше», номера прогонов без однозначности.

---

## 8. Миграция при смене платформы (BDS → VPS)

- Стартовый промпт не меняется.
- Пути в `read_meta_file` не меняются (относительно `_meta/`).
- Транскрипт вызовов — на стороне сервера, по `call_id`.
- `validate_answer` — на стороне сервера.

**Проектная совместимость:** MCP v2 без привязки к локальным путям, конфиг через env.

---

## 9. Распаковка ZIP

**Распаковщик универсальный:** `$targetDir = "C:\ai_workSpaceGitHub"`. В этой папке лежат **два** клона:
- `C:\ai_workSpaceGitHub\ai_workspace` — публичный репозиторий
- `C:\ai_workSpaceGitHub\ai_workspace_projects` — приватный репозиторий

**Агент формирует ZIP с префиксом репозитория:**
- `ai_workspace/_meta/design/...` → попадёт в `C:\ai_workSpaceGitHub\ai_workspace\_meta\design\...`
- `ai_workspace_projects/...` → попадёт в `C:\ai_workSpaceGitHub\ai_workspace_projects\...`

**Если агент упакует без префикса** (`_meta/...`) — файлы лягут в `C:\ai_workSpaceGitHub\_meta\...`, мимо обоих репозиториев. Это главная причина «файлы не ложатся как надо».

### 9.1. Главные причины сбоя

1. **Застревание на битом ZIP** (старый батник, один `try` на распаковку + удаление).
2. **Race condition** (`timeout /t 3` вслепую).
3. **Берётся не тот ZIP** (`for %%F` без сортировки по времени).
4. **ZIP без префикса репозитория** (§4 — главное).

### 9.2. Что делать при сбое

1. Посмотреть `C:\dsh-out\unzip.log`.
2. «ZIP невалиден», `.bad` — удалить `.bad`, перегенерировать ZIP.
3. «Распаковано», но файлов нет в `ai_workspace` — проверить `C:\ai_workSpaceGitHub\_meta` (корень). Если файлы там — ZIP без префикса, перегенерировать.
4. ZIP не удалился — закрыть в проводнике, подождать 5 с.
5. `C:\dsh-out` пуст — проверить `Downloads`.

### 9.3. Надёжный скрипт

См. `15-zipper.md` §3. Ключевое: `$targetDir = "C:\ai_workSpaceGitHub"` (универсально, не меняется под проект).

### 9.4. Требования к формированию ZIP (со стороны агента)

| Репозиторий | Правильный путь в ZIP |
|---|---|
| `ai_workspace` | `ai_workspace/_meta/design/00-START-HERE-v2.md` |
| `ai_workspace` | `ai_workspace/kb/unf30/...` |
| `ai_workspace_projects` | `ai_workspace_projects/...` |

**Неправильно:** `_meta/design/...`, `kb/unf30/...` (без префикса — ляжет в корень `C:\ai_workSpaceGitHub`).

### 9.5. Проверка после распаковки

- [ ] `C:\dsh-out` пуст (или только `unzip.log`).
- [ ] `unzip.log`: последняя запись «ZIP удалён», в entries есть префикс `ai_workspace/`.
- [ ] `C:\ai_workSpaceGitHub\ai_workspace\_meta\design\` — новые файлы.
- [ ] `C:\ai_workSpaceGitHub\_meta` — **не существует** (если есть — ZIP без префикса, удалить, перегенерировать).
- [ ] `git -C C:\ai_workSpaceGitHub\ai_workspace status` — ожидаемые изменения.
