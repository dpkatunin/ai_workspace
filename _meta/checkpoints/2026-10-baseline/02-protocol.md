# Протокол baseline (секция 2 чекпоинта)

Заполняет оператор, одна строка на вопрос, по ходу прогона.

**Колонка `fix_hypothesis` предзаполнена** — это прогноз из эталона (`06-expected-routing.md`), а не факт. Если по факту гипотеза не подтвердилась — правьте её прямо в таблице.
Знак `?` в гипотезе = предположение, требующее проверки содержимого `by-synonym.md` / `by-movement.md` (в этот пакет они не входят).

**failure_class:** `navigation` (пошёл не туда) / `synonym` (не нашёл по разговорному слову) / `movement` (не нашёл регистр→документ) / `format` (нашёл, но ответ неудобен) / `missing_card` (карточки нет) / `source_leak` (обратился в `_source/`).

| № | Открытые файлы (порядок) | Цитированные id | Top-1 | Top-3 | failure_class | citation_ok | fix_hypothesis (прогноз) | Комментарий |
|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  | цепочка `pb-otgruzka-s-rezervom` → `mech-rezervirovanie` → `doc-zakaz-pokupatelya`; ожидаемо теряется object. Проверить cross-links из playbook в object |  |
| 2 |  |  |  |  |  |  | ожидаем hit `pit-rezervirovanie` |  |
| 3 |  |  |  |  |  |  | ожидаемо теряется `cat-specifikaciya`. Кандидат: `by-synonym: +спецификация`? или cross-link из `pb-vypusk-produkcii` |  |
| 4 |  |  |  |  |  |  | ожидаемо теряется `pb-sebestoimost-rabot` при hit `pit-raboty`. Кандидат: cross-link из pitfall в playbook |  |
| 5 |  |  |  |  |  |  | ожидаемо теряется `doc-prikhodnaya-nakladnaya` при hit `mech-ordernaya-shema`. Кандидат: `by-movement: +приходная накладная → регистр ордерной схемы`? |  |
| 6 |  |  |  |  |  |  | ожидаем hit `pit-sklad` |  |
| 7 |  |  |  |  |  |  | ожидаем hit `doc-dopolnitelnye-rashody` + `pit-zakupki` |  |
| 8 |  |  |  |  |  |  | ожидаем hit `doc-korrektirovka-postupleniya` + `pit-zakupki` |  |
| 9 |  |  |  |  |  |  | ожидаем hit `pit-ceny` + `doc-ustanovka-cen`; **обе draft** — проверить, что агент в ответе явно назвал статус |  |
| 10 |  |  |  |  |  |  | ожидаем hit `mech-skidki-nacenki` (draft); индекс `by-synonym` не проверялся — гипотеза `?` |  |
| 11 |  |  |  |  |  |  | ожидаем hit `pit-dengi` (draft) + `cat-kassy` (draft); проверить явное указание статуса |  |
| 12 |  |  |  |  |  |  | ожидаем hit `mech-bank-ekvayring` (draft); проверить явное указание статуса |  |
| 13 |  |  |  |  |  |  | прогноз **miss**: `doc-zakaz-pokupatelya` и `doc-zakaz-na-proizvodstvo` без синонимов. Кандидат: `by-synonym: +заказ покупателя`, `+заказ на производство`? |  |
| 14 |  |  |  |  |  |  | прогноз partial: «зарплата» вне синонимов `doc-sdelnyy-naryad`. Кандидат: `by-synonym: +зарплата → doc-sdelnyy-naryad`? |  |
| 15 |  |  |  |  |  |  | прогноз **miss**: нет строки `→ doc-ustanovka-cen` в `by-movement`. Кандидат: `by-movement: +регистр «Цены номенклатуры» → doc-ustanovka-cen`? |  |

## Сводка (заполнить после прогона)

- Top-1 hit: __/15
- Top-3 hit: __/15
- source_leak: __
- ответов без id/статуса: __
- «запросил ≠ процитировал»: __
- draft-карточек, использованных в ответах: __ (из них агент явно назвал статус: __)
