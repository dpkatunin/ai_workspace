# 1С:УНФ 3.0 — индекс раздела

## Состав

| Папка | Что | Примеры карточек |
|---|---|---|
| `objects/` | Документы, справочники, регистры | `doc-realizaciya`, `doc-proizvodstvo`, `cat-specifikaciya`, `doc-zakaz-na-proizvodstvo`, `doc-zakaz-pokupatelya`, `doc-prikhodnaya-nakladnaya`, `doc-zakaz-naryad`, `doc-akt-vypolnennyh-rabot`, `doc-sdelnyy-naryad`, `cat-nomenklatura` |
| `mechanisms/` | Сквозные механизмы | `mech-rezervirovanie` |
| `playbooks/` | Процедуры | `pb-otgruzka-s-rezervom`, `pb-vypusk-produkcii`, `pb-sebestoimost-rabot` |
| `pitfalls/` | Кластеры грабель | `pit-rezervirovanie`, `pit-proizvodstvo`, `pit-specifikacii`, `pit-raboty` |
| `cases/` | Паттерны из внедрений | `case-mebel-nestandart` |

## Приоритет наполнения

Фаза 2:
1. Контур **работ**: акт, сдельный наряд, грабли — закрыто этим спринтом.
2. Углубление **торгового контура**: склад (ордерная схема, ячейки), закупки (доп. расходы, корректировки), ценообразование.
3. **Кейсы** из `_source/` (15 шт. — по одному).

## Готовые карточки

### Объекты
- `unf30-doc-realizaciya` — Расходная накладная (эталон объекта).
- `unf30-doc-proizvodstvo` — Производство / Сборка запасов.
- `unf30-cat-specifikaciya` — Спецификации (рецепты изделий).
- `unf30-doc-zakaz-na-proizvodstvo` — Заказ на производство (план).
- `unf30-doc-zakaz-pokupatelya` — Заказ покупателя (обязательство и резерв).
- `unf30-doc-prikhodnaya-nakladnaya` — Приходная накладная (поступление).
- `unf30-doc-zakaz-naryad` — Заказ-наряд (выполнение работ).
- `unf30-doc-akt-vypolnennyh-rabot` — Акт выполненных работ.
- `unf30-doc-sdelnyy-naryad` — Сдельный наряд (зарплата).
- `unf30-cat-nomenklatura` — Справочник «Номенклатура» (типы для работ).

### Механизмы
- `unf30-mech-rezervirovanie` — Резервирование запасов (жёсткий резерв).

### Процедуры (playbooks)
- `unf30-pb-otgruzka-s-rezervom` — отгрузка с резервом (эталон playbook).
- `unf30-pb-vypusk-produkcii` — выпуск продукции (приоритет).
- `unf30-pb-sebestoimost-rabot` — расчёт себестоимости работ.

### Грабли (pitfalls)
- `unf30-pit-rezervirovanie` — резервы (эталон pitfall).
- `unf30-pit-proizvodstvo` — производство (приоритет).
- `unf30-pit-specifikacii` — спецификации.
- `unf30-pit-raboty` — контур работ.

### Кейсы
- `unf30-case-mebel-nestandart` — мебельное производство (эталон кейса).

## Как добавить карточку

См. `_meta/conventions.md`. Шаблоны — в `templates/`.
