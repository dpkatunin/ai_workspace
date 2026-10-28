<!-- Ручной индекс. По ADR-003 будет генерироваться из поля `synonyms` фронтматтера карточек. -->
# Индекс синонимов

Быстрый переход: разговорное слово → ID карточки.

| Синоним | ID карточки | Тип |
|---|---|---|
| реализация, отгрузка, расходная накладная | `unf30-doc-realizaciya` | object |
| резерв, зарезервировано, резервирование | `unf30-mech-rezervirovanie` | mechanism |
| резерв не списывается, грабли резервов | `unf30-pit-rezervirovanie` | pitfall |
| отгрузка с резервом | `unf30-pb-otgruzka-s-rezervom` | playbook |
| выпуск продукции, производство продукции | `unf30-pb-vypusk-produkcii` | playbook |
| сборка, документ «Производство» | `unf30-doc-proizvodstvo` | object |
| спецификация, рецепт | `unf30-cat-specifikaciya` | object |
| сдельщина, сдельный наряд, наряд, выработка, зарплата | `unf30-doc-sdelnyy-naryad` | object |
| акт выполненных работ, акт, закрывающий документ | `unf30-doc-akt-vypolnennyh-rabot` | object |
| себестоимость работ, затраты на работы | `unf30-pb-sebestoimost-rabot` | playbook |
| мебель, нестандарт, индивидуальные заказы | `unf30-case-mebel-nestandart` | case |
| ордер, ордерная схема, приходный ордер, расходный ордер | `unf30-mech-ordernaya-shema` | mechanism |
| склады, склад, розничный склад, подразделение | `unf30-cat-sklady` | object |
| инвентаризация, пересортица, ячейки | `unf30-pit-sklad` | pitfall |
| допрасходы, доставка, погрузка, дополнительные расходы | `unf30-doc-dopolnitelnye-rashody` | object |
| корректировка поступления, исправить приход, акт о расхождениях | `unf30-doc-korrektirovka-postupleniya` | object |
| закупки, возврат поставщику, принять больше заказа | `unf30-pit-zakupki` | pitfall |
| установка цен, виды цен, цена номенклатуры, прайс | `unf30-doc-ustanovka-cen` | object |
| скидки, наценки, условия скидок, дисконт, акция | `unf30-mech-skidki-nacenki` | mechanism |
| цена не подтянулась, ндс в цене, округление цены, скидка не сработала | `unf30-pit-ceny` | pitfall |
| касса, кассовые документы, пко, рко, подотчёт, авансовый отчёт | `unf30-cat-kassy` | object |
| банк, банковский счёт, платёжное поручение, эквайринг, оплата картой, поступление на счёт | `unf30-mech-bank-ekvayring` | mechanism |
| деньги, касса не закрывается, подотчётник не отчитался, комиссия эквайринга, выписка не загружена | `unf30-pit-dengi` | pitfall |
| заказ покупателя, заказ клиента | `unf30-doc-zakaz-pokupatelya` | object |
| заказ на производство | `unf30-doc-zakaz-na-proizvodstvo` | object |
| приходная, поступление | `unf30-doc-prikhodnaya-nakladnaya` | object |
| заказ-наряд | `unf30-doc-zakaz-naryad` | object |
| номенклатура, товар, услуга | `unf30-cat-nomenklatura` | object |
| контрагент, юрлицо, ИП, контрагент-физлицо | `unf30-cat-kontragent` | object |
| взаиморасчёты, задолженность, долг, акт сверки, зачёт, корректировка долга | `unf30-mech-vzaimoraschety` | mechanism |
| дубль контрагента, два контрагента с одним ИНН, контрагент не находится, договор не подтягивается, контрагент не выбирается | `unf30-pit-kontragenty` | pitfall |
