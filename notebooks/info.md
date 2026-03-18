## 📁 Файл: `notebooks/research.py`

### Назначение

Класс для анализа данных и визуализации результатов в Jupyter notebooks. Позволяет получать статистику, строить графики и экспортировать данные.

### Класс `OlfactoryResearch`

#### Конструктор

```python
def __init__(self, db_path="data/olfactory.db"):
    self.db = OlfactoryDB(db_path)        # подключение к БД
    self.languages = self.db.texts.languages  # языки из TextManager
```

---

### Основные методы

#### 1. Получение данных

| Метод                              | Назначение                                      | Возвращает                                                                       |
| --------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `get_texts_dataframe(language=None)`  | Все тексты в виде таблицы            | DataFrame с колонками: id, title, author, year, language, text_type, smell_count |
| `get_smells_dataframe(language=None)` | Все слова-запахи в виде таблицы | DataFrame с колонками: text_id, title, author, language, word, lemma, pos        |

#### 2. Визуализация

| Метод                                 | Назначение                      | Что показывает                                                    |
| ------------------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------------ |
| `plot_smell_distribution(language=None)` | Распределение запахов | 3 графика: гистограмма, топ-10 текстов, scatter    |
| `plot_top_smells(language=None, n=20)`   | Самые частые запахи      | Столбчатая диаграмма                                        |
| `compare_languages()`                    | Сравнение языков           | 4 графика: среднее, максимум, сумма, процент |

#### 3. Поиск и анализ

| Метод                                                | Назначение                                           | Возвращает                                        |
| --------------------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------- |
| `search_by_smell(smell_word, language=None)`            | Найти тексты с конкретным запахом | DataFrame с текстами и предложениями |
| `get_smell_statistics_by_author(author, language=None)` | Статистика по автору                         | DataFrame со словами-запахами              |

#### 4. Экспорт

| Метод                                 | Назначение                     |
| ------------------------------------------ | ---------------------------------------- |
| `export_to_csv(table_name, output_file)` | Сохранить таблицу в CSV |

---

### Сценарии использования в Jupyter

#### Базовый анализ

```python
# 1. Загружаем класс
from notebooks.research import OlfactoryResearch
research = OlfactoryResearch("data/olfactory.db")

# 2. Смотрим общую статистику
df = research.get_texts_dataframe()
print(f"Всего текстов: {len(df)}")
print(df.groupby('language')['smell_count'].sum())

# 3. Строим графики
research.plot_smell_distribution('ru')
research.plot_top_smells('ru', n=30)
research.compare_languages()
```

#### Поиск конкретного запаха

```python
# Найти все упоминания "яблоко"
results = research.search_by_smell("яблоко", language='ru')

# Показать результаты
for _, row in results.iterrows():
    print(f"📖 {row['title']} - {row['author']}")
    print(f"💬 {row['sentence']}\n")
```

#### Анализ автора

```python
# Статистика по Достоевскому
dostoevsky = research.get_smell_statistics_by_author("Достоевский")

# Топ-10 запахов у автора
dostoevsky['smell_word'].value_counts().head(10).plot(kind='bar')
plt.show()
```

#### Экспорт данных для отчета

```python
# Выгрузить все русские запахи
research.export_to_csv('olfactory_ru', 'отчет_запахи.csv')

# Выгрузить все тексты
research.export_to_csv('texts_ru', 'отчет_тексты.csv')
```

---

### Важные замечания

1. **Заглушки** - `token_count` и `smell_ratio` не используются (всегда 0)
2. **Языки** - берутся из `TextManager`, синхронизация автоматическая
3. **JSON парсинг** - `smell_words` автоматически преобразуется из JSON
4. **Выравнивание** - методы для работы с выравниванием отсутствуют (только в `OlfactoryManager`)

---

### Типичные ошибки

| Ошибка                           | Причина                                             | Решение                                                               |
| -------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `KeyError: 'sentence'`               | В `search_by_smell` нет поля `sentence`        | Проверить метод (должен добавлять `sentence`) |
| Пустой DataFrame                 | Нет данных для выбранного языка | Проверить, есть ли тексты в БД                       |
| График не показывает | Нет данных или все `smell_count = 0`      | Загрузить тексты через `processors.py`                 |
