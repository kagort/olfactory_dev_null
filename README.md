## Быстрый старт

### 1. Создание виртуального окружения

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Загрузка моделей spaCy

```bash
python -m spacy download ru_core_news_sm
python -m spacy download en_core_web_sm
```

### 4. Полная сборка корпуса

```bash
python run.py sborka
```

Эта команда последовательно выполняет:

- создание базы данных
- применение миграций
- загрузку книг из CSV
- связывание переводов
- поиск ольфакторных предложений

### 5. Ручное выравнивание предложений

```bash
# Посмотреть список текстов с ID
python run.py list-align

# Экспорт для выравнивания (ru_id en_id)
python run.py export-align 1 1

# Импорт размеченного файла
python run.py import-align results/alignment.xlsx
```

### 6. Запуск Jupyter для анализа (в процессе)

```bash
python run.py jupyter
```

## Доступные команды

* С данными командами можно ознакомиться в run.py

| Команда                      | Описание                                                                                                                                                                   |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python run.py sborka`            | Полная сборка корпуса                                                                                                                                           |
| `python run.py db`                | Создать базу данных                                                                                                                                               |
| `python run.py migrate`           | Применить миграции                                                                                                                                                |
| `python run.py ingest`            | Загрузить книги из CSV                                                                                                                                             |
| `python run.py link`              | Связать переводы с оригиналами                                                                                                                          |
| `python run.py check`             | Проверить несвязанные переводы                                                                                                                         |
| `python run.py detect`            | Найти ольфакторные предложения                                                                                                                         |
| `python run.py detect --clear`    | Найти (с очисткой таблицы)                                                                                                                                    |
| `python run.py list-align`        | Показать все тексты с ID                                                                                                                                         |
| `python run.py export-align 1 1 ` | Экспорт для выравнивания<br />Под 1 1 подразумеваются индексы<br />текста_оригинала и текста_перевода |
| `python run.py import-align`      | Импорт размеченных пар                                                                                                                                         |
| `python run.py backup`            | Создать бекап базы данных                                                                                                                                    |
| `python run.py reset`             | Полный сброс (с бекапом)                                                                                                                                        |
| `python run.py jupyter`           | Запустить Jupyter Notebook                                                                                                                                                |

## Структура проекта

```
olfactory-corpus/
│
├── db/                         # База данных
│   ├── schemas/                # SQL-схемы (версии)
│   ├── migrations/             # Миграции БД
│   ├── backups/                # Автоматические бекапы
│   ├── create_db.py            # Создание БД
│   ├── migrate.py              # Применение миграций
│   ├── backup.py               # Бекап и восстановление
│   └── olfactory.db            # Файл базы данных (создаётся автоматически)
│
├── data/                       # Данные
│   ├── books/                  # Исходные тексты
│   │   └── raw/                # .txt файлы книг
│   └── metadata.csv            # Метаданные: file, lang, type, author, title, translator, original_id
│
├── src/                        # Исходный код
│   ├── config.py               # Конфигурация (пути, словари запахов)
│   ├── ingest.py               # Загрузка книг из CSV
│   ├── processing.py           # Поиск ольфакторных предложений
│   ├── alignment.py            # Экспорт/импорт для выравнивания
│   └── ...                     # Другие модули
│
├── notebooks/                  # Jupyter ноутбуки для анализа
│   └── analysis.ipynb
│
├── results/                    # Результаты (создаётся автоматически)
│   ├── alignment.xlsx          # Файл для ручного выравнивания
│   └── full_dataset.xlsx       # Экспортированный датасет
│
├── run.py                      # Главный управляющий скрипт
├── requirements.txt            # Зависимости Python
└── README.md                   # Этот файл
```

## Формат CSV с метаданными (`data/metadata.csv`)

| Колонка  | Описание                                  | Пример             |
| --------------- | ------------------------------------------------- | ------------------------ |
| `file`        | Имя файла в `data/books/raw/`          | `war_and_peace_ru.txt` |
| `lang`        | Язык (`ru` или `en`)                   | `ru`                   |
| `type`        | `original` или `translation`               | `translation`             |
| `author`      | Автор                                        | `Толстой`       |
| `title`       | Название                                  | `Peace and war` |
| `original_title` | Название оригинала (для переводов) | `Война и пир` | 
| `translator`  | Переводчик (для переводов)  | `Maude`                |
| `original_id` | ID оригинала (для переводов) | `1`                    |

## Требования

- Python 3.9+
- SQLite3
- Виртуальное окружение (рекомендуется)
