# 1С:УНФ 3.0 — индекс раздела

## Состав

| Папка | Что | Примеры карточек |
|---|---|---|
| `objects/` | Документы, справочники, регистры | `doc-realizaciya`, `doc-proizvodstvo`, `cat-specifikaciya`, `doc-zakaz-na-proizvodstvo`, `doc-zakaz-pokupatelya`, `doc-prikhodnaya-nakladnaya`, `doc-zakaz-naryad`, `doc-akt-vypolnennyh-rabot`, `doc-sdelnyy-naryad`, `doc-dopolnitelnye-rashody`, `doc-korrektirovka-postupleniya`, `doc-ustanovka-cen`, `cat-kassy`, `cat-nomenklatura`, `cat-sklady`, `cat-kontragent` |
| `mechanisms/` | Сквозные механизмы | `mech-rezervirovanie`, `mech-ordernaya-shema`, `mech-skidki-nacenki`, `mech-bank-ekvayring`, `mech-vzaimoraschety` |
| `playbooks/` | Процедуры | `pb-otgruzka-s-rezervom`, `pb-vypusk-produkcii`, `pb-sebestoimost-rabot` |
| `pitfalls/` | Кластеры грабель | `pit-rezervirovanie`, `pit-proizvodstvo`, `pit-specifikacii`, `pit-raboty`, `pit-sklad`, `pit-zakupki`, `pit-ceny`, `pit-dengi`, `pit-kontragenty` |
| `cases/` | Паттерны из внедрений | `case-mebel-nestandart` |

## Готовые карточки

### Объекты
- `unf30-doc-realizaciya` — Расходная накладная (эталон объекта). Покрывает: отгрузку, продажи, расчёты с покупателями.
- `unf30-doc-proizvodstvo` — Производство / Сборка запасов. Покрывает: выпуск продукции, движения по регистру «Запасы».
- `unf30-cat-specifikaciya` — Спецификации (рецепты изделий). Покрывает: состав изделия.
- `unf30-doc-zakaz-na-proizvodstvo` — Заказ на производство (план). Покрывает: планирование производства.
- `unf30-doc-zakaz-pokupatelya` — Заказ покупателя (обязательство и резерв). Покрывает: резервирование под клиента.
- `unf30-doc-prikhodnaya-nakladnaya` — Приходная накладная (поступление). Покрывает: закупки, расчёты с поставщиками.
- `unf30-doc-zakaz-naryad` — Заказ-наряд (выполнение работ). Покрывает: контур работ.
- `unf30-doc-akt-vypolnennyh-rabot` — Акт выполненных работ. Покрывает: закрытие работ.
- `unf30-doc-sdelnyy-naryad` — Сдельный наряд. Покрывает: фиксацию выработки и начисление зарплаты (Дт 20.40 Кт 70).
- `unf30-doc-dopolnitelnye-rashody` — Дополнительные расходы. Покрывает: доставку, погрузку.
- `unf30-doc-korrektirovka-postupleniya` — Корректировка поступления. Покрывает: исправление приходных документов.
- `unf30-doc-ustanovka-cen` — Установка цен номенклатуры (черновик). Покрывает: виды цен, прайс.
- `unf30-cat-kassy` — Кассы и кассовый контур (черновик). Покрывает: кассовые документы.
- `unf30-cat-nomenklatura` — Справочник «Номенклатура». Покрывает: товары, услуги.
- `unf30-cat-sklady` — Справочник «Склады и магазины». Покрывает: склады.
- `unf30-cat-kontragent` — Справочник «Контрагенты» (черновик). Покрывает: реквизиты, роли покупатель/поставщик, договоры, группы.

### Механизмы
- `unf30-mech-rezervirovanie` — Резервирование запасов. Покрывает: жёсткий резерв.
- `unf30-mech-ordernaya-shema` — Ордерная схема. Покрывает: приходные и расходные ордера.
- `unf30-mech-skidki-nacenki` — Скидки и наценки (черновик). Покрывает: условия скидок.
- `unf30-mech-bank-ekvayring` — Банк и эквайринг (черновик). Покрывает: оплату картой, платёжные поручения.
- `unf30-mech-vzaimoraschety` — Взаиморасчёты с контрагентами (черновик). Покрывает: связку «контрагент + договор», регистры расчётов, закрытие задолженности.

### Процедуры (playbooks)
- `unf30-pb-otgruzka-s-rezervom` — отгрузка с резервом (эталон playbook). Покрывает: цепочку отгрузки.
- `unf30-pb-vypusk-produkcii` — выпуск продукции. Покрывает: производство по спецификации.
- `unf30-pb-sebestoimost-rabot` — расчёт себестоимости работ. Покрывает: затраты на работы.

### Грабли (pitfalls)
- `unf30-pit-rezervirovanie` — резервы. Покрывает: почему не списывается.
- `unf30-pit-proizvodstvo` — производство.
- `unf30-pit-specifikacii` — спецификации.
- `unf30-pit-raboty` — контур работ.
- `unf30-pit-sklad` — склад.
- `unf30-pit-zakupki` — закупки.
- `unf30-pit-ceny` — цены, скидки, наценки (черновик).
- `unf30-pit-dengi` — касса, банк, эквайринг, подотчёт (черновик).
- `unf30-pit-kontragenty` — контрагенты (черновик). Покрывает: дубли, пустой выбор, договор не подтягивается.

### Кейсы
- `unf30-case-mebel-nestandart` — мебельное производство (эталон кейса).

## Как добавить карточку

См. `_meta/conventions.md`. Шаблоны — в `templates/`.
Синонимы объявляются полем `synonyms` во фронтматтере (ADR-001), а не правкой `by-synonym.md` руками.
