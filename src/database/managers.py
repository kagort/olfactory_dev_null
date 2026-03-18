import json
from typing import List, Dict, Optional, Any, Union


class TableManager:
    """Создание и управление таблицами"""
    def __init__(self, db):
        self.db = db
        self.languages = ['ru', 'en', 'de']
    
    def create_all(self):
        """Создает все нужные таблицы"""
        
        # 1. Таблицы текстов для каждого языка (оставляем как есть)
        for lang in self.languages:
            self.db.execute(f'''
                CREATE TABLE IF NOT EXISTS texts_{lang} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    year INTEGER,
                    content TEXT NOT NULL,
                    text_type TEXT NOT NULL CHECK(text_type IN ('original', 'translation')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.db.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_texts_{lang}_author 
                ON texts_{lang}(author)
            ''')
            self.db.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_texts_{lang}_year 
                ON texts_{lang}(year)
            ''')
        
        # 2. Таблица связей между текстами (оставляем)
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS text_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_lang TEXT NOT NULL,
                original_id INTEGER NOT NULL,
                translation_lang TEXT NOT NULL,
                translation_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(original_lang, original_id, translation_lang, translation_id)
            )
        ''')
        
        # 3. НОВЫЕ таблицы только для ольфакторных предложений (вместо sentences_*)
        for lang in self.languages:
            self.db.execute(f'''
                CREATE TABLE IF NOT EXISTS olfactory_{lang} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    sentence TEXT NOT NULL,
                    smell_words TEXT,  -- JSON со словами-запахами
                    left_context TEXT,
                    right_context TEXT,
                    
                    type TEXT CHECK(type IN ('direct', 'metaphor')),
                    connotation TEXT, 
                    tonal TEXT CHECK(tonal IN ('positive', 'negative', 'neutral')),
                    gramm_structure TEXT,
                    comments TEXT,
                    
                    verified BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (text_id) REFERENCES texts_{lang}(id) ON DELETE CASCADE
                )
            ''')
            
            self.db.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_olfactory_{lang}_text 
                ON olfactory_{lang}(text_id)
            ''')
            self.db.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_olfactory_{lang}_position 
                ON olfactory_{lang}(position)
            ''')
        
        # 4. Таблица выравнивания ТОЛЬКО для ольфакторных предложений
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS olfactory_alignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ru_id INTEGER NOT NULL,
                en_id INTEGER NOT NULL,
                verified BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ru_id) REFERENCES olfactory_ru(id) ON DELETE CASCADE,
                FOREIGN KEY (en_id) REFERENCES olfactory_en(id) ON DELETE CASCADE,
                UNIQUE(ru_id, en_id)
            )
        ''')
        
        print("📊 Все таблицы успешно созданы")

class TextManager:
    """Работа с текстами"""
    def __init__(self, db):
        self.db = db
        self.languages = ['ru', 'en', 'de']
    
    def _get_table(self, language):
        """Возвращает имя таблицы для языка"""
        if language not in self.languages:
            raise ValueError(f"Язык {language} не поддерживается")
        return f"texts_{language}"
    
    def add_original(self, language, title, author, year, content):
        """Добавить оригинальный текст"""
        table = self._get_table(language)
        return self.db.execute(
            f"INSERT INTO {table} (title, author, year, content, text_type) VALUES (?, ?, ?, ?, 'original')",
            (title, author, year, content)
        )
    
    def add_translation(self, language, title, author, year, content, original_lang, original_id):
        """Добавить перевод"""
        table = self._get_table(language)
        
        # Добавляем перевод
        trans_id = self.db.execute(
            f"INSERT INTO {table} (title, author, year, content, text_type) VALUES (?, ?, ?, ?, 'translation')",
            (title, author, year, content)
        )
        
        # Связываем с оригиналом
        self.db.execute(
            "INSERT INTO text_relations (original_lang, original_id, translation_lang, translation_id) VALUES (?, ?, ?, ?)",
            (original_lang, original_id, language, trans_id)
        )
        
        return trans_id
    
    def get_by_id(self, language, text_id):
        """Получить текст по ID"""
        table = self._get_table(language)
        result = self.db.execute(f"SELECT * FROM {table} WHERE id = ?", (text_id,))
        return result[0] if result else None
    
    def get_by_language(self, language, text_type=None):
        """Получить все тексты на языке"""
        table = self._get_table(language)
        if text_type:
            return self.db.execute(
                f"SELECT * FROM {table} WHERE text_type = ? ORDER BY author, year",
                (text_type,)
            )
        return self.db.execute(f"SELECT * FROM {table} ORDER BY author, year")
    
    def get_by_author(self, author, language):
        """Поиск текстов по автору"""
        table = self._get_table(language)
        return self.db.execute(
            f"SELECT * FROM {table} WHERE author LIKE ? ORDER BY year",
            (f"%{author}%",)
        )
    
    def get_by_year_range(self, start_year, end_year, language):
        """Получить тексты за период"""
        table = self._get_table(language)
        return self.db.execute(
            f"SELECT * FROM {table} WHERE year BETWEEN ? AND ? ORDER BY year",
            (start_year, end_year)
        )
    
    def get_translations(self, original_lang, original_id):
        """Получить все переводы текста"""
        relations = self.db.execute(
            "SELECT * FROM text_relations WHERE original_lang = ? AND original_id = ?",
            (original_lang, original_id)
        )
        
        translations = []
        for rel in relations:
            table = self._get_table(rel['translation_lang'])
            text = self.db.execute(
                f"SELECT * FROM {table} WHERE id = ?",
                (rel['translation_id'],)
            )
            if text:
                text[0]['language'] = rel['translation_lang']
                translations.append(text[0])
        
        return translations
    
    def get_original(self, translation_lang, translation_id):
        """Найти оригинал для перевода"""
        relations = self.db.execute(
            "SELECT * FROM text_relations WHERE translation_lang = ? AND translation_id = ?",
            (translation_lang, translation_id)
        )
        
        if relations:
            rel = relations[0]
            table = self._get_table(rel['original_lang'])
            text = self.db.execute(
                f"SELECT * FROM {table} WHERE id = ?",
                (rel['original_id'],)
            )
            if text:
                text[0]['language'] = rel['original_lang']
                return text[0]
        return None
    
    def delete(self, language, text_id):
        """Удалить текст"""
        table = self._get_table(language)
        
        # Удаляем связи
        self.db.execute(
            "DELETE FROM text_relations WHERE (original_lang = ? AND original_id = ?) OR (translation_lang = ? AND translation_id = ?)",
            (language, text_id, language, text_id)
        )
        
        # Удаляем текст
        return self.db.execute(f"DELETE FROM {table} WHERE id = ?", (text_id,))

class DummyDict:
    """Заглушка для словаря, если он не нужен"""
    def __init__(self):
        pass
    
    def check(self, word, language):
        return False
    
    def get_all(self, language=None):
        return []
    
    def add(self, word, language):
        return True
    

class OlfactoryManager:
    """Работа с ольфакторными предложениями"""
    def __init__(self, db):
        self.db = db
        self.languages = ['ru', 'en', 'de']
        

    def _get_table(self, language: str) -> str:
        """Получить имя таблицы для языка"""
        if language not in self.languages:
            raise ValueError(f"Язык {language} не поддерживается")
        return f"olfactory_{language}"
    
    def _parse_smell_words(self, data: Optional[Dict]) -> Optional[Dict]:
        """Разобрать JSON с запахами"""
        if data and data.get('smell_words'):
            try:
                data['smell_words'] = json.loads(data['smell_words'])
            except (json.JSONDecodeError, TypeError):
                pass
        return data
    
    def _validate_text_exists(self, language: str, text_id: int) -> bool:
        """Проверить, существует ли текст"""
        result = self.db.execute(
            f"SELECT id FROM texts_{language} WHERE id = ?",
            (text_id,)
        )
        return bool(result)
    
    def add(self, language: str, text_id: int, position: int, sentence: str,
            smell_words: list = None, left_context: str = None, 
            right_context: str = None, verified: bool = False,
            type_val: str = None, connotation: str = None, 
            tonal: str = None, gramm_structure: str = None,
            comments: str = None) -> int:
        """
        Добавить ОДНО ольфакторное предложение
        
        Args:
            language: язык
            text_id: ID текста
            position: позиция в тексте
            sentence: текст предложения
            smell_words: список слов-запахов
            left_context: левый контекст
            right_context: правый контекст
            verified: проверено ли
            type_val: тип ('direct' или 'metaphor')
            connotation: коннотация
            tonal: тональность
            gramm_structure: грамматическая структура
            comments: комментарии
            
        Returns:
            int: ID добавленного предложения
        """
        # Проверяем язык
        if language not in self.languages:
            raise ValueError(f"Язык {language} не поддерживается")
        
        # Проверяем существование текста
        if not self._validate_text_exists(language, text_id):
            raise ValueError(f"Текст с id {text_id} не существует в языке {language}")
        
        # Подготавливаем smell_words в JSON
        if smell_words is None:
            smell_words_json = None
        elif isinstance(smell_words, (list, dict)):
            smell_words_json = json.dumps(smell_words, ensure_ascii=False)
        else:
            smell_words_json = str(smell_words)
        
        table = f"olfactory_{language}"
        
        # Вставляем запись
        cursor = self.db.conn.execute(f"""
            INSERT INTO {table} 
            (text_id, position, sentence, smell_words, left_context, right_context,
             type, connotation, tonal, gramm_structure, comments, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (text_id, position, sentence, smell_words_json, 
              left_context, right_context, type_val, connotation,
              tonal, gramm_structure, comments, 1 if verified else 0))
        
        result = cursor.fetchone()
        self.db.conn.commit()
        
        return result[0] if result else None
    
    def add_many(self, language: str, sentences_list: List[tuple]) -> None:
        """
        Добавить несколько предложений сразу
        
        Args:
            language: язык
            sentences_list: список кортежей с данными предложений
                Каждый кортеж должен содержать:
                (text_id, position, sentence, [smell_words], [left_context], 
                 [right_context], [type], [connotation], [tonal], 
                 [gramm_structure], [comments], [verified])
        """
        table = self._get_table(language)
        
        values = []
        for s in sentences_list:
            text_id = s[0]
            
            # Проверяем текст
            if not self._validate_text_exists(language, text_id):
                raise ValueError(f"Текст с id {text_id} не существует в языке {language}")
            
            # Распаковываем с дефолтными значениями
            position = s[1]
            sentence = s[2]
            smell_words = s[3] if len(s) > 3 else None
            left_context = s[4] if len(s) > 4 else None
            right_context = s[5] if len(s) > 5 else None
            type_val = s[6] if len(s) > 6 else None
            connotation = s[7] if len(s) > 7 else None
            tonal = s[8] if len(s) > 8 else None
            gramm_structure = s[9] if len(s) > 9 else None
            comments = s[10] if len(s) > 10 else None
            verified = s[11] if len(s) > 11 else False
            
            if isinstance(smell_words, (list, dict)):
                smell_words = json.dumps(smell_words, ensure_ascii=False)
            
            values.append((text_id, position, sentence, smell_words, 
                          left_context, right_context, type_val, connotation,
                          tonal, gramm_structure, comments, 1 if verified else 0))
        
        self.db.executemany(f"""
            INSERT INTO {table} 
            (text_id, position, sentence, smell_words, left_context, right_context,
             type, connotation, tonal, gramm_structure, comments, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)
    
    def get_by_id(self, language: str, olf_id: int) -> Optional[Dict]:
        """Получить ольфакторное предложение по ID"""
        table = self._get_table(language)
        result = self.db.execute(f"SELECT * FROM {table} WHERE id = ?", (olf_id,))
        
        if result:
            return self._parse_smell_words(result[0])
        return None
    
    def get_by_text(self, language: str, text_id: int) -> List[Dict]:
        """Получить все ольфакторные предложения текста"""
        table = self._get_table(language)
        results = self.db.execute(
            f"SELECT * FROM {table} WHERE text_id = ? ORDER BY position",
            (text_id,)
        )
        
        for r in results:
            self._parse_smell_words(r)
        return results
    
    def get_by_text_and_position(self, language: str, text_id: int, position: int) -> Optional[Dict]:
        """Получить предложение по тексту и позиции"""
        table = self._get_table(language)
        result = self.db.execute(
            f"SELECT * FROM {table} WHERE text_id = ? AND position = ?",
            (text_id, position)
        )
        
        if result:
            return self._parse_smell_words(result[0])
        return None
    
    def search_by_smell_word(self, language: str, word: str) -> List[Dict]:
        """Найти все предложения, содержащие слово-запах"""
        table = self._get_table(language)
        results = self.db.execute(
            f"SELECT * FROM {table} WHERE smell_words LIKE ?",
            (f'%"{word}"%',)  # Ищем точное слово в JSON
        )
        
        for r in results:
            self._parse_smell_words(r)
        return results
    
    def update(self, language: str, olf_id: int, **kwargs) -> bool:
        """
        Обновить поля предложения
        
        Args:
            language: язык
            olf_id: ID предложения
            **kwargs: поля для обновления
                Можно обновлять: smell_words, left_context, right_context,
                type, connotation, tonal, gramm_structure, comments, verified
        """
        table = self._get_table(language)
        
        # Разрешенные поля для обновления
        allowed_fields = [
            'smell_words', 'left_context', 'right_context',
            'type', 'connotation', 'tonal', 'gramm_structure', 
            'comments', 'verified'
        ]
        
        # Формируем запрос динамически
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field not in allowed_fields:
                continue
                
            if field == 'smell_words' and isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            elif field == 'verified':
                value = 1 if value else 0
            
            updates.append(f"{field} = ?")
            values.append(value)
        
        if not updates:
            return False
        
        values.append(olf_id)
        query = f"UPDATE {table} SET {', '.join(updates)} WHERE id = ?"
        
        return bool(self.db.execute(query, values))
    
    def update_smell_words(self, language: str, olf_id: int, 
                          smell_words: Union[List, Dict, str]) -> bool:
        """Обновить список слов-запахов"""
        return self.update(language, olf_id, smell_words=smell_words)
    
    def mark_verified(self, language: str, olf_id: int, verified: bool = True) -> bool:
        """Отметить предложение как проверенное"""
        return self.update(language, olf_id, verified=verified)
    
    def delete(self, language: str, olf_id: int) -> bool:
        """Удалить ольфакторное предложение"""
        table = self._get_table(language)
        return bool(self.db.execute(f"DELETE FROM {table} WHERE id = ?", (olf_id,)))
    
    def delete_by_text(self, language: str, text_id: int) -> bool:
        """Удалить все предложения текста"""
        table = self._get_table(language)
        return bool(self.db.execute(
            f"DELETE FROM {table} WHERE text_id = ?", 
            (text_id,)
        ))
    
    # Методы для работы с выравниванием (alignments)
    
    def align(self, ru_id: int, en_id: int, verified: bool = False) -> None:
        """Связать русское и английское ольфакторные предложения"""
        self.db.execute("""
            INSERT OR REPLACE INTO olfactory_alignments (ru_id, en_id, verified)
            VALUES (?, ?, ?)
        """, (ru_id, en_id, 1 if verified else 0))
    
    def get_aligned(self, from_lang: str, from_id: int, to_lang: str) -> Optional[Dict]:
        """
        Получить соответствие для предложения
        
        Args:
            from_lang: язык исходного предложения
            from_id: ID исходного предложения
            to_lang: язык целевого предложения
        """
        if from_lang == 'ru' and to_lang == 'en':
            result = self.db.execute("""
                SELECT o_en.* FROM olfactory_alignments a
                JOIN olfactory_en o_en ON a.en_id = o_en.id
                WHERE a.ru_id = ?
            """, (from_id,))
        elif from_lang == 'en' and to_lang == 'ru':
            result = self.db.execute("""
                SELECT o_ru.* FROM olfactory_alignments a
                JOIN olfactory_ru o_ru ON a.ru_id = o_ru.id
                WHERE a.en_id = ?
            """, (from_id,))
        else:
            raise ValueError(f"Неподдерживаемая пара языков: {from_lang} -> {to_lang}")
        
        if result:
            return self._parse_smell_words(result[0])
        return None
    
    def get_aligned_en(self, ru_id: int) -> Optional[Dict]:
        """Получить английское соответствие для русского предложения"""
        return self.get_aligned('ru', ru_id, 'en')
    
    def get_aligned_ru(self, en_id: int) -> Optional[Dict]:
        """Получить русское соответствие для английского предложения"""
        return self.get_aligned('en', en_id, 'ru')
    
    def get_unaligned(self, language: str, text_id: Optional[int] = None) -> List[Dict]:
        """
        Получить предложения без соответствия
        
        Args:
            language: язык ('ru' или 'en')
            text_id: если указан, только для конкретного текста
        """
        if language == 'ru':
            query = """
                SELECT o.* FROM olfactory_ru o
                LEFT JOIN olfactory_alignments a ON o.id = a.ru_id
                WHERE a.ru_id IS NULL
            """
            params = []
        elif language == 'en':
            query = """
                SELECT o.* FROM olfactory_en o
                LEFT JOIN olfactory_alignments a ON o.id = a.en_id
                WHERE a.en_id IS NULL
            """
            params = []
        else:
            raise ValueError(f"Язык {language} не поддерживается для выравнивания")
        
        if text_id:
            query += f" AND o.text_id = ?"
            params.append(text_id)
        
        query += " ORDER BY o.position"
        
        results = self.db.execute(query, tuple(params))
        for r in results:
            self._parse_smell_words(r)
        return results
    
    def get_unaligned_ru(self, text_id: Optional[int] = None) -> List[Dict]:
        """Получить русские предложения без английского соответствия"""
        return self.get_unaligned('ru', text_id)
    
    # Статистика и экспорт
    
    def get_statistics(self, language: str, text_id: Optional[int] = None) -> Dict:
        """
        Получить статистику по ольфакторным предложениям
        """
        table = self._get_table(language)
        
        if text_id:
            stats = self.db.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) as verified,
                    SUM(CASE WHEN type = 'direct' THEN 1 ELSE 0 END) as direct,
                    SUM(CASE WHEN type = 'metaphor' THEN 1 ELSE 0 END) as metaphor,
                    SUM(CASE WHEN tonal = 'positive' THEN 1 ELSE 0 END) as positive,
                    SUM(CASE WHEN tonal = 'negative' THEN 1 ELSE 0 END) as negative,
                    SUM(CASE WHEN tonal = 'neutral' THEN 1 ELSE 0 END) as neutral,
                    AVG(json_array_length(smell_words)) as avg_smells,
                    COUNT(DISTINCT smell_words) as unique_smell_patterns
                FROM {table}
                WHERE text_id = ?
            """, (text_id,))[0]
        else:
            stats = self.db.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT text_id) as texts,
                    SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) as verified,
                    SUM(CASE WHEN type = 'direct' THEN 1 ELSE 0 END) as direct,
                    SUM(CASE WHEN type = 'metaphor' THEN 1 ELSE 0 END) as metaphor,
                    SUM(CASE WHEN tonal = 'positive' THEN 1 ELSE 0 END) as positive,
                    SUM(CASE WHEN tonal = 'negative' THEN 1 ELSE 0 END) as negative,
                    SUM(CASE WHEN tonal = 'neutral' THEN 1 ELSE 0 END) as neutral,
                    AVG(json_array_length(smell_words)) as avg_smells,
                    COUNT(DISTINCT smell_words) as unique_smell_patterns
                FROM {table}
            """)[0]
        
        # Преобразуем None в 0
        return {k: v or 0 for k, v in stats.items()}
    
    def get_smell_words_frequency(self, language: str, text_id: Optional[int] = None) -> Dict[str, int]:
        """
        Получить частотность слов-запахов
        """
        table = self._get_table(language)
        
        if text_id:
            results = self.db.execute(
                f"SELECT smell_words FROM {table} WHERE text_id = ? AND smell_words IS NOT NULL",
                (text_id,)
            )
        else:
            results = self.db.execute(
                f"SELECT smell_words FROM {table} WHERE smell_words IS NOT NULL"
            )
        
        frequency = {}
        for r in results:
            if r['smell_words']:
                try:
                    words = json.loads(r['smell_words'])
                    if isinstance(words, list):
                        for word in words:
                            frequency[word] = frequency.get(word, 0) + 1
                except:
                    pass
        
        return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True))
    
    def export_to_csv(self, language: str, text_id: Optional[int] = None) -> List[Dict]:
        """
        Экспортировать данные для CSV анализа
        """
        if text_id:
            query = f"""
                SELECT 
                    t.id as txt_ID,
                    t.title as txt_title,
                    t.author as txt_author,
                    t.year as txt_year,
                    t.text_type,
                    o.position as sent_position,
                    o.sentence as sent_text,
                    o.smell_words,
                    o.left_context,
                    o.right_context,
                    o.type,
                    o.connotation,
                    o.tonal,
                    o.gramm_structure,
                    o.comments,
                    o.verified
                FROM olfactory_{language} o
                JOIN texts_{language} t ON o.text_id = t.id
                WHERE o.text_id = ?
                ORDER BY o.position
            """
            results = self.db.execute(query, (text_id,))
        else:
            query = f"""
                SELECT 
                    t.id as txt_ID,
                    t.title as txt_title,
                    t.author as txt_author,
                    t.year as txt_year,
                    t.text_type,
                    o.position as sent_position,
                    o.sentence as sent_text,
                    o.smell_words,
                    o.left_context,
                    o.right_context,
                    o.type,
                    o.connotation,
                    o.tonal,
                    o.gramm_structure,
                    o.comments,
                    o.verified
                FROM olfactory_{language} o
                JOIN texts_{language} t ON o.text_id = t.id
                ORDER BY t.id, o.position
            """
            results = self.db.execute(query)
        
        # Парсим JSON для удобства
        for r in results:
            if r['smell_words']:
                try:
                    r['smell_words'] = json.loads(r['smell_words'])
                except:
                    pass
        
        return results

    def export_alignment_csv(self, ru_text_id: int, en_text_id: int, 
                            output_path: str = None) -> str:
        """
        Экспортирует выровненные ольфакторные предложения в CSV
        
        Args:
            ru_text_id: ID русского текста
            en_text_id: ID английского перевода
            output_path: путь для сохранения CSV
        
        Returns:
            str: путь к созданному CSV файлу
        """
        import pandas as pd
        from pathlib import Path
        import json
        
        # 1. Получаем все русские предложения
        ru_sentences = self.get_by_text('ru', ru_text_id)
        
        # 2. Получаем все английские предложения
        en_sentences = self.get_by_text('en', en_text_id)
        en_by_id = {s['id']: s for s in en_sentences}
        
        # 3. Получаем все выравнивания
        alignments = self.db.execute("""
            SELECT ru_id, en_id, verified as alignment_verified
            FROM olfactory_alignments
            WHERE ru_id IN (SELECT id FROM olfactory_ru WHERE text_id = ?)
            AND en_id IN (SELECT id FROM olfactory_en WHERE text_id = ?)
        """, (ru_text_id, en_text_id))
        
        alignment_map = {a['ru_id']: a['en_id'] for a in alignments}
        
        # 4. Формируем данные для CSV
        rows = []
        
        for ru_sent in ru_sentences:
            en_id = alignment_map.get(ru_sent['id'])
            en_sent = en_by_id.get(en_id) if en_id else None
            
            # Парсим слова-запахи
            ru_words = self._parse_smell_words_to_list(ru_sent.get('smell_words', []))
            en_words = self._parse_smell_words_to_list(en_sent.get('smell_words', [])) if en_sent else []
            
            # Определяем максимальное количество токенов
            max_tokens = max(len(ru_words), len(en_words))
            
            for i in range(max_tokens):
                # Русский токен
                ru_word = ru_words[i] if i < len(ru_words) else {}
                en_word = en_words[i] if i < len(en_words) else {}
                
                row = {
                    # Русская часть
                    'txt_ID': ru_sent['text_id'],
                    'case_iD': ru_sent['text_id'],  # или что-то другое?
                    'sent_ID': ru_sent['id'],
                    'sent_text_RU': ru_sent['sentence'] if i == 0 else '',
                    'token_ID': i + 1,
                    'token_RU': ru_word.get('word', ''),
                    'token_pos': ru_word.get('pos', ''),
                    'concept_unit_RU': ru_word.get('concept', ru_word.get('word', '')),
                    'type_RU': ru_sent.get('type', ''),
                    'connotation_RU': ru_sent.get('connotation', ''),
                    'IntensityRU': '',
                    'tonality_RU': ru_sent.get('tonal', ''),
                    'gram_structureRU': ru_sent.get('gramm_structure', ''),
                    'comments_RU': ru_sent.get('comments', ''),
                    
                    # Английская часть
                    'trans_text_ID': en_sent['text_id'] if en_sent else '',
                    'txt_ID_en': en_sent['text_id'] if en_sent else '',
                    'sent_text_EN': en_sent['sentence'] if en_sent and i == 0 else '',
                    'concept_unit_EN': en_word.get('concept', en_word.get('word', '')),
                    'token_EN': en_word.get('word', ''),
                    'token_pos_EN': en_word.get('pos', ''),
                    'gram.structure_EN': en_sent.get('gramm_structure', '') if en_sent else '',
                    'type_EN': en_sent.get('type', '') if en_sent else '',
                    'connotation_EN': en_sent.get('connotation', '') if en_sent else '',
                    'intensity_EN': '',
                    'tonality_EN': en_sent.get('tonal', '') if en_sent else '',
                    'comments_EN': en_sent.get('comments', '') if en_sent else '',
                    
                    # Метаданные
                    'translation_shift': 'aligned' if en_sent else 'not_aligned',
                    'cosine_sim_LaBSE': '',
                    'shift_notes': '',
                    'verified': ru_sent.get('verified', 0) and (en_sent.get('verified', 0) if en_sent else 0)
                }
                rows.append(row)
        
        # 5. Создаем DataFrame
        df = pd.DataFrame(rows)
        
        # 6. Сохраняем
        if output_path is None:
            ru_text = self.db.texts.get_by_id('ru', ru_text_id)
            en_text = self.db.texts.get_by_id('en', en_text_id)
            
            ru_title = ru_text['title'][:30].replace(' ', '_') if ru_text else f"ru_{ru_text_id}"
            en_title = en_text['title'][:30].replace(' ', '_') if en_text else f"en_{en_text_id}"
            
            output_path = f"alignment_{ru_title}_to_{en_title}.csv"
        
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✅ CSV сохранен: {output_path}")
        print(f"📊 Всего строк: {len(df)}")
        
        return output_path

def _parse_smell_words_to_list(self, smell_words):
    """Вспомогательный метод для парсинга smell_words в список"""
    if isinstance(smell_words, str):
        try:
            return json.loads(smell_words)
        except:
            return []
    elif isinstance(smell_words, list):
        return smell_words
    return []
        
    def get_context(self, language: str, olf_id: int, window: int = 100) -> Optional[Dict]:
        """
        Получить предложение с расширенным контекстом
        
        Args:
            language: язык
            olf_id: ID предложения
            window: сколько символов контекста слева и справа
        """
        olf = self.get_by_id(language, olf_id)
        if not olf:
            return None
        
        # Получаем полный текст
        text_result = self.db.execute(
            f"SELECT content FROM texts_{language} WHERE id = ?",
            (olf['text_id'],)
        )
        if not text_result:
            return olf
        
        full_text = text_result[0]['content']
        
        # Ищем предложение в тексте (упрощенно)
        sentence = olf['sentence']
        pos = full_text.find(sentence)
        
        if pos >= 0:
            # Вырезаем контекст
            start = max(0, pos - window)
            end = min(len(full_text), pos + len(sentence) + window)
            
            context_text = full_text[start:end]
            
            # Добавляем ... если обрезали
            if start > 0:
                context_text = '...' + context_text
            if end < len(full_text):
                context_text = context_text + '...'
        else:
            context_text = sentence
        
        return {
            **olf,
            'full_text_excerpt': context_text
        }