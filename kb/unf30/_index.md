# 1С:УНФ 3.0 — индекс раздела

## Состав

| Папка | Что | Примеры карточек |
|---|---|---|
| `objects/` | Документы, справочники, регистры | `doc-realizaciya`, `doc-proizvodstvo`, `cat-specifikaciya`, `doc-zakaz-na-proizvodstvo`, `doc-zakaz-pokupatelya`, `doc-prikhodnaya-nakladnaya`, `doc-zakaz-naryad`, `doc-akt-vypolnennyh-rabot`, `doc-sdelnyy-naryad`, `doc-dopolnitelnye-rashody`, `doc-korrektirovka-postupleniya`, `doc-ustanovka-cen`, `cat-nomenklatura`, `cat-sklady` |
| `mechanisms/` | Сквозные механизмы | `mech-rezervirovanie`, `mech-ordernaya-shema`, `mech-skidki-nacenki` |
| `playbooks/` | Процедуры | `pb-otgruzka-s-rezervom`, `pb-vypusk-produkcii`, `pb-sebestoimost-rabot` |
| `pitfalls/` | Кластеры грабель | `pit-rezervirovanie`, `pit-proizvodstvo`, `pit-specifikacii`, `pit-raboty`, `pit-sklad`, `pit-zakupki`, `pit-ceny` |
| `cases/` | Паттерны из внедрений | `case-mebel-nestandart` |

## Приоритет наполнения

Фаза 2 (цель — полный торговый контур, см. `handover.md`):
1. Контур **работ**: акт, сдельный наряд, грабли — закрыто.
2. **Склад**: ордерная схема, справочник складов, грабли — закрыто.
3. **Закупки**: доп. расходы, корректировка поступления, грабли — закрыто.
4. **Ценообразование**: виды цен, установка цен, скидки/наценки, грабли — закрыто этим спринтом.
5. **Деньги**: касса, банк, эквайринг, подотчёт. ← **следующий спринт**
6. **Контрагенты/договоры**: базовая карточка + грабли.
7. **Кейсы** из `_source/` (по 2 за спринт).

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
- `unf30-doc-dopolnitelnye-rashody` — Дополнительные расходы.
- `unf30-doc-korrektirovka-postupleniya` — Корректировка поступления.
- `unf30-doc-ustanovka-cen` — Установка цен номенклатуры (черновик, спринт 4).
- `unf30-cat-nomenklatura` — Справочник «Номенклатура» (типы для работ).
- `unf30-cat-sklady` — Справочник «Склады и магазины».

### Механизмы
- `unf30-mech-rezervirovanie` — Резервирование запасов (жёсткий резерв).
- `unf30-mech-ordernaya-shema` — Ордерная схема.
- `unf30-mech-skidki-nacenki` — Скидки и наценки (черновик, спринт 4).

### Процедуры (playbooks)
- `unf30-pb-otgruzka-s-rezervom` — отгрузка с резервом (эталон playbook).
- `unf30-pb-vypusk-produkcii` — выпуск продукции.
- `unf30-pb-sebestoimost-rabot` — расчёт себестоимости работ.

### Грабли (pitfalls)
- `unf30-pit-rezervirovanie` — резервы (эталон pitfall).
- `unf30-pit-proizvodstvo` — производство.
- `unf30-pit-specifikacii` — спецификации.
- `unf30-pit-raboty` — контур работ.
- `unf30-pit-sklad` — склад.
- `unf30-pit-zakupki` — закупки.
- `unf30-pit-ceny` — цены, скидки, наценки (черновик, спринт 4).

### Кейсы
- `unf30-case-mebel-nestandart` — мебельное производство (эталон кейса).

## Как добавить карточку

См. `_meta/conventions.md`. Шаблоны — в `templates/`.
