**Ольфакторный анализатор текстов** — инструмент для поиска, аннотирования и выравнивания слов-запахов в художественных текстах на русском и английском языках.

**Основные возможности:**
- Автоматический поиск предложений с запахами (spaCy + словарь)
- Сохранение контекста и грамматической информации
- Ручное выравнивание русских и английских ольфакторных предложений через Excel
- Экспорт данных для статистического анализа

---

## 🗂️ СТРУКТУРА ПРОЕКТА (кратко)

```
ваш_проект/
├── 📁 notebooks/           # Исследования
│   ├── test.ipynb          # Jupyter ноутбук для анализа
│   └── research.py         # Класс для графиков и статистики
│
├── 📁 src/                  # Исходный код
│   ├── 📁 database/         # Работа с БД
│   │   ├── __init__.py
│   │   ├── core.py          # Подключение к SQLite
│   │   └── managers.py      # Классы: TableManager, TextManager, OlfactoryManager и др.
│   │
│   ├── 📁 processors/       # Обработка текстов
│   │   ├── __init__.py
│   │   └── processor.py     # Класс FileProcessor (поиск запахов)
│   │
│   └── __init__.py
│
├── 📁 data/                  # База данных
│   └── olfactory.db
│
├── console.py                # Консольное меню
└── requirements.txt          # Зависимости
```

---

## Два способа работы

---

### 1. КОНСОЛЬ (`console.py`)

**Для чего:** быстрая загрузка файлов, ручное выравнивание через Excel, базовые операции

**Запуск:**
```bash
python console.py
```
---

### 2. JUPYTER (`notebooks/test.ipynb`)

**Для чего:** аналитика, графики, статистика, сложные запросы

**Основные команды:**
```python
# Подключение
from notebooks.research import OlfactoryResearch
research = OlfactoryResearch("data/olfactory.db")

# Посмотреть данные
df = research.get_texts_dataframe('ru')
df.head()

# Графики
research.plot_smell_distribution('ru')
research.plot_top_smells('ru', n=20)
research.compare_languages()

# Поиск
results = research.search_by_smell("яблоко", 'ru')
results[['title', 'sentence']]

# Экспорт
research.export_to_csv('olfactory_ru', 'данные.csv')
```

---

### 🔄 Сравнение способов

| Задача | Консоль | Jupyter |
|--------|---------|---------|
| Загрузить новый текст | ✅ (меню) | ✅ (через `processor`) |
| Посмотреть список текстов | ✅ | ✅ |
| Экспорт в Excel для выравнивания | ✅ | (возможно) |
| Импорт из Excel | ✅ | (возможно) |
| Построить график | ❌ | ✅ |
| Детальная статистика | ✅ (базовая) | ✅ (подробная) |
| Сравнить языки | ❌ | ✅ |
| Сохранить исследование | ❌ | ✅ (весь notebook) |
| Пакетная обработка | ✅ | ✅ |

---

### ⚠️ Важно

**После изменения кода в файлах (.py):**
- Для консоли: просто перезапустить `console.py`
- Для Jupyter: **Kernel → Restart** (обязательно!)

**Где данные:** `data/olfactory.db` — база данных со всеми текстами и аннотациями

**Где словарь запахов:** `src/processors/processor.py`, переменная `OLFACTORY_WORDS`

**Виртуальное окружение (рекомендуется)**

```bash
# Создать окружение
python -m venv venv

# Активировать
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```
**Установка из `requirements.txt`**

```txt
spacy>=3.0.0
syntok>=1.4.0
pandas>=1.5.0
openpyxl>=3.0.0
```
**Установка моделей spaCy**

После установки spacy нужно скачать языковые модели:

```bash
# Русская модель (≈ 50 МБ)
python -m spacy download ru_core_news_sm

# Английская модель (≈ 50 МБ)
python -m spacy download en_core_web_sm
```

**Если скачивание через `spacy download` не работает:**

```bash
# Через pip напрямую
pip install https://github.com/explosion/spacy-models/releases/download/ru_core_news_sm-3.7.0/ru_core_news_sm-3.7.0-py3-none-any.whl

pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.0/en_core_web_sm-3.7.0-py3-none-any.whl
```

---




## 📄 `managers.py` — Методы для работы с БД

### Базовые классы

| Класс | Назначение |
|-------|------------|
| `BaseManager` | Базовый класс для всех менеджеров. Обеспечивает: универсальный поиск (`find`, `find_one`), получение имени таблицы по языку (`_get_language_table`), проверку существования текста (`_validate_text_exists`) |
| `TableManager` | Создание всех таблиц БД: `texts_{lang}`, `text_relations`, `sent_{lang}`, `olfactory_alignments`, `olfactory_words_{lang}` |

---

### `TextManager` — работа с текстами

| Метод | Описание | Пример |
|-------|----------|--------|
| `add_original(lang, title, author, year, content)` | Добавить оригинальный текст | `db.texts.add_original('ru', 'Война и мир', 'Толстой', 1869, text)` |
| `add_translation(lang, title, author, translator, year, content, orig_lang, orig_id)` | Добавить перевод с привязкой к оригиналу | `db.texts.add_translation('en', 'War and Peace', 'Tolstoy', 'Briggs', 2005, text, 'ru', 1)` |
| `get_translations(orig_lang, orig_id)` | Получить все переводы текста | `db.texts.get_translations('ru', 1)` |
| `get_original(trans_lang, trans_id)` | Найти оригинал по переводу | `db.texts.get_original('en', 2)` |
| `get_by_language(lang, text_type)` | Получить все тексты на языке | `db.texts.get_by_language('ru', 'original')` |
| `delete(lang, text_id)` | Удалить текст и его связи | `db.texts.delete('ru', 1)` |

---

### `OlfactoryManager` — работа с ольфакторными предложениями

| Метод | Описание | Пример |
|-------|----------|--------|
| `add(lang, text_id, position, sentence, smell_words, ...)` | Добавить предложение и его слова-запахи | `db.olfactory.add('ru', 1, 5, "Пахло яблоками", [{'word':'пахло'}])` |
| `find(lang, **filters)` | Поиск предложений по фильтрам | `db.olfactory.find('ru', text_id=1, verified=1)` |
| `update(lang, olf_id, **kwargs)` | Обновить аннотации | `db.olfactory.update('ru', 10, type='metaphor', tonal='positive')` |
| `delete(lang, olf_id)` | Удалить предложение | `db.olfactory.delete('ru', 10)` |
| `delete_by_text(lang, text_id)` | Удалить все предложения текста | `db.olfactory.delete_by_text('ru', 1)` |

---

### `AlignmentHelper` — выравнивание предложений

| Метод | Описание | Пример |
|-------|----------|--------|
| `export_for_alignment(ru_text_id, en_text_id, output_path, only_unmatched)` | Экспорт в Excel для ручного выравнивания. Создает листы: русские (невыровненные), английские (справочник), статистика | `db.alignment.export_for_alignment(2, 1)` |
| `import_alignment_from_excel(excel_path, ru_text_id, en_text_id, clear_existing)` | Импорт выравниваний из Excel. `clear_existing=True` — удаляет старые перед импортом | `db.alignment.import_alignment_from_excel('alignment.xlsx', ru_text_id=2)` |

---

### `CsvExporter` — экспорт данных

| Метод | Описание | Пример |
|-------|----------|--------|
| `export_aligned_data(output_path, ru_text_id, en_text_id)` | Экспорт выровненных предложений в CSV. Если указаны оба ID — только для пары текстов, иначе — все выровненные пары | `db.csv.export_aligned_data('data.csv', ru_text_id=2, en_text_id=1)` |

---

### Таблицы БД

| Таблица | Назначение |
|---------|------------|
| `texts_{ru/en/de}` | Хранит тексты: id, title, author, translator, year, content, text_type (original/translation) |
| `text_relations` | Связи оригинал-перевод: original_lang, original_id, translation_lang, translation_id |
| `sent_{ru/en/de}` | Ольфакторные предложения: text_id, sentence, position, smell_word, left_context, right_context, type, connotation, tonal, gramm_structure, comments, verified |
| `olfactory_words_{ru/en/de}` | Слова-запахи: olf_id (ссылка на sent), word, lemma, pos, children, concept |
| `olfactory_alignments` | Выравнивания русских и английских предложений: ru_id, en_id, verified |

---

### Инициализация

```python
from database import OlfactoryDB

db = OlfactoryDB("data/olfactory.db")
db.init()  # создает все таблицы

# Использование
db.texts.add_original('ru', 'Анна Каренина', 'Толстой', 1877, content)
db.olfactory.find('ru', text_id=1)

db.close()
```

## 📄 `file_processor.py` — Обработка текстов и поиск запахов

### Назначение
Автоматический поиск и аннотирование предложений с запахами в текстах с использованием spaCy.

---

### Класс `FileProcessor`

| Метод | Описание | Пример |
|-------|----------|--------|
| `__init__(db)` | Инициализация с подключением к БД | `processor = FileProcessor(db)` |

---

### Загрузка и обработка

| Метод | Описание | Пример |
|-------|----------|--------|
| `process_file(file_path, title, author, translator, year, language, is_original, original_lang, original_id)` | Загрузить файл, разбить на предложения, найти запахи, сохранить в БД | `processor.process_file('text.txt', title='Роман', author='Автор', language='ru', is_original=True)` |
| `process_text(text, title, author, year, language, is_original, original_lang, original_id)` | Обработать текст напрямую (без файла) | `processor.process_text(text, title='Ручной ввод')` |
| `reanalyze_text(text_id, language)` | Повторно проанализировать текст (после расширения словаря) | `processor.reanalyze_text(1, 'ru')` |

---

### Внутренние методы (анализ)

| Метод | Описание |
|-------|----------|
| `_detect_language(text)` | Определяет язык по первым 1000 символам (кириллица → ru, иначе en) |
| `_split_sentences(text)` | Разбивает текст на предложения с помощью `syntok` |
| `_get_nlp_model(language)` | Ленивая загрузка модели spaCy (`ru_core_news_sm` / `en_core_web_sm`) |
| `_extract_context(words, word_pos, window=3)` | Извлекает левый и правый контекст для слова (по 3 слова в каждую сторону) |
| `_analyze_sentence(sentence, text_id, position, language)` | Анализирует предложение: быстрая проверка на слова-запахи, затем spaCy-анализ. Возвращает словарь с найденными словами, контекстом и словосочетанием |

---

### Словарь запахов `OLFACTORY_WORDS`

| Язык | Слова |
|------|-------|
| **ru** | запах, аромат, вонь, пахнуть, душистый, пахучий, воняет, благоухает и др. |
| **en** | smell, scent, odor, aroma, fragrance, stink, reek, smelled, fragrant, odorous и др. |

---

### Типичный сценарий

```python
from database import OlfactoryDB
from processors import FileProcessor

# Подключение к БД
db = OlfactoryDB("data/olfactory.db")
db.init()

# Создание процессора
processor = FileProcessor(db)

# Загрузка файла
result = processor.process_file(
    file_path="data/texts/anna_karenina.txt",
    title="Анна Каренина",
    author="Лев Толстой",
    year=1877,
    language="ru",
    is_original=True
)

print(f"Добавлен текст ID: {result['text_id']}")
print(f"Найдено предложений с запахами: {result['olfactory_sentences']}")

# Закрытие БД
db.close()
```

---

### Особенности

| Особенность | Описание |
|-------------|----------|
| **Ленивая загрузка моделей** | Модель spaCy загружается только при первом использовании языка |
| **Двухэтапный анализ** | Сначала быстрая проверка по словарю, затем глубокий анализ через spaCy |
| **Контекст** | Сохраняет до 3 слов слева и справа от слова-запаха |
| **Словосочетание** | Извлекает фразу целиком (concept phrase) |
| **Повторный анализ** | Можно доанализировать текст после расширения словаря |

---

### ⚠️ Важно

- Требует установки моделей spaCy:
  ```bash
  python -m spacy download ru_core_news_sm
  python -m spacy download en_core_web_sm
  ```
- Поддерживаются только русский и английский языки
- Кодировка файлов: UTF-8

## 📄 `console.py` — Консольное меню

### Назначение
Интерактивный интерфейс для загрузки текстов, выравнивания и экспорта данных.

---

### Запуск

```bash
python console.py [путь_к_БД]
# Пример: python console.py data/olfactory.db
```

---

### Главное меню

| Пункт | Описание |
|-------|----------|
| `[1]` | 📂 Загрузка файлов |
| `[2]` | 🔗 Выравнивание ольфакторных предложений |
| `[0]` | 🚪 Выход |

---

### Меню загрузки файлов (пункт 1)

| Пункт | Метод | Описание |
|-------|-------|----------|
| `[1]` | `load_file('original')` | Загрузить оригинальный текст из файла |
| `[2]` | `load_file('translation')` | Загрузить перевод из файла (с привязкой к оригиналу) |
| `[3]` | `load_multiple_files()` | Пакетная загрузка нескольких файлов (все как оригиналы) |
| `[4]` | `load_parallel_files()` | Загрузить пару (оригинал + перевод) одновременно |
| `[5]` | `reanalyze_text()` | Повторный анализ текста после расширения словаря |
| `[0]` | — | Назад |

---

### Меню выравнивания (пункт 2)

| Пункт | Метод | Описание |
|-------|-------|----------|
| `[1]` | `show_alignable_pairs()` | Показать пары текстов, которые можно выровнять |
| `[2]` | `export_for_alignment()` | Экспорт в Excel для ручного выравнивания (шаблон) |
| `[3]` | `import_alignment_from_excel()` | Импорт выравниваний из заполненного Excel |
| `[4]` | `export_aligned_data()` | Экспорт выровненных данных в CSV |
| `[0]` | — | Назад |


---

### Вспомогательные методы

| Метод | Описание |
|-------|----------|
| `_select_language(prompt)` | Выбор языка из списка (ru/en/de) с проверкой |
| `_ask_metadata(ask_translator, ask_language)` | Запрос метаданных: название, автор, переводчик, год |
| `clear_screen()` | Очистка экрана |
| `print_header()` | Вывод шапки с названием и путем к БД |

---

### ⚠️ Особенности

| Особенность | Описание |
|-------------|----------|
| **Очистка экрана** | Работает на Windows (`cls`) и Linux/Mac (`clear`) |
| **Обработка ошибок** | Блоки try/except при вводе чисел и загрузке файлов |
| **Пауза** | `input()` после каждого действия для удобства чтения |
| **Пути к файлам** | Относительные/абсолютные — любые |
| **Пакетная загрузка** | Можно загрузить несколько файлов за раз |
| **Повторный анализ** | Находит новые запахи после расширения словаря |

---

### 🗂️ Структура папок (рекомендуемая)

```
ваш_проект/
├── data/
│   ├── olfactory.db
│   └── csv/
│       └── alignment_*.xlsx
├── src/
│   ├── database/
│   └── processors/
└── console.py
```