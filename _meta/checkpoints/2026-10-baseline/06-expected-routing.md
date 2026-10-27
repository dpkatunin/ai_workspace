# Эталон маршрутизации (секция 4 чекпоинта)

> ⚠️ **НЕ ПЕРЕДАВАТЬ АГЕНТУ-ПОД-ТЕСТОМ.** Файл содержит ожидаемые id — если агент его увидит, baseline недействителен.
> Читает только архитектор и оператор.

| № | Ожидаемая навигация | Что проверяем | Прогноз |
|---|---|---|---|
| 1 | `pb-otgruzka-s-rezervom` → `mech-rezervirovanie` → `doc-zakaz-pokupatelya` | Цепочка playbook→mechanism→object | playbook hit, object потеряется |
| 2 | `pit-rezervirovanie` | Pitfall routing | hit |
| 3 | `pb-vypusk-produkcii`, `doc-proizvodstvo`, `cat-specifikaciya` | Ambiguity object/playbook | partial: `cat-specifikaciya` потеряется |
| 4 | `pit-raboty`, `pb-sebestoimost-rabot` | Pitfall vs playbook | partial: playbook потеряется |
| 5 | `mech-ordernaya-shema`, `doc-prikhodnaya-nakladnaya` | Mechanism→object | partial: object потеряется |
| 6 | `pit-sklad` | Pitfall | hit |
| 7 | `doc-dopolnitelnye-rashody`, `pit-zakupki` | Object + pitfall | hit |
| 8 | `doc-korrektirovka-postupleniya`, `pit-zakupki` | Correction object | hit |
| 9 | `pit-ceny`, `doc-ustanovka-cen` | Draft pitfall + object | hit, но draft |
| 10 | `mech-skidki-nacenki` | Draft mechanism | hit |
| 11 | `pit-dengi`, `cat-kassy` | Draft pitfall + object | hit |
| 12 | `mech-bank-ekvayring` | Draft mechanism | hit |
| 13 | `doc-zakaz-pokupatelya`, `doc-zakaz-na-proizvodstvo` | Disambiguation | **miss**: оба без синонимов |
| 14 | `doc-sdelnyy-naryad` | Object, «зарплата» вне синонимов | partial |
| 15 | `by-movement` → `doc-ustanovka-cen` | Полнота `by-movement` | **miss**: строки нет |

**Резервный вопрос:** «Зарезервировать товар под заказ» → `mech-rezervirovanie` vs `pit-rezervirovanie` (ловушка mechanism/pitfall).
