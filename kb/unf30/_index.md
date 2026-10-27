# 1С:УНФ 3.0 — индекс раздела

## Состав

| Папка | Что | Примеры карточек |
|---|---|---|
| `objects/` | Документы, справочники, регистры | `doc-realizaciya`, `doc-proizvodstvo`, `cat-specifikaciya`, `doc-zakaz-na-proizvodstvo`, `doc-zakaz-pokupatelya`, `doc-prikhodnaya-nakladnaya`, `doc-zakaz-naryad`, `cat-nomenklatura` |
| `mechanisms/` | Сквозные механизмы | `mech-rezervirovanie` |
| `playbooks/` | Процедуры | `pb-otgruzka-s-rezervom`, `pb-vypusk-produkcii`, `pb-sebestoimost-rabot` |
| `pitfalls/` | Кластеры грабель | `pit-rezervirovanie`, `pit-proizvodstvo`, `pit-specifikacii` |
| `cases/` | Паттерны из внедрений | `case-mebel-nestandart` |

## Приоритет наполнения

Фаза 2 идёт по контуру **производство и работы**:
1. Производство: спецификации, заказ, выпуск, себестоимость, брак, давальческое сырьё.
2. Работы: заказ-наряд, акт, сдельная зарплата, распределение затрат.
3. Затем — торговый контур: продажи, закупки, склад, деньги.

## Готовые карточки

### Объекты
- `unf30-doc-realizaciya` — Расходная накладная (эталон объекта).
- `unf30-doc-proizvodstvo` — Производство / Сборка запасов.
- `unf30-cat-specifikaciya` — Спецификации (рецепты изделий).
- `unf30-doc-zakaz-na-proizvodstvo` — Заказ на производство (план).
- `unf30-doc-zakaz-pokupatelya` — Заказ покупателя (обязательство и резерв).
- `unf30-doc-prikhodnaya-nakladnaya` — Приходная накладная (поступление).
- `unf30-doc-zakaz-naryad` — Заказ-наряд (выполнение работ).
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

### Кейсы
- `unf30-case-mebel-nestandart` — мебельное производство (эталон кейса).

## Как добавить карточку

См. `_meta/conventions.md`. Шаблоны — в `templates/`.
