import json
from typing import List, Dict, Optional, Any, Union

class BaseManager:
    def __init__(self, db):
        self.db = db
        self.languages = ['ru', 'en', 'de']
        self.table_base_name = None
    
    def _get_language_table(self, language: str) -> str:
        # base_name берется из self.table_base_name
        if self.__class__.table_base_name is None:
            raise NotImplementedError("table_base_name не установлен")
        if language not in self.languages:
            raise ValueError(f"Язык {language} не поддерживается")
        return f"{self.__class__.table_base_name}_{language}"

    def _validate_text_exists(self, language, **criteria):
        # тут в качестве валидатора можно использовать любое поле из таблицы text, начиная с id, заканчивая временем создания
        if not criteria:
            return False
        conditions = [f"{k} = ?" for k in criteria.keys()]
        params = list(criteria.values())
        query = f"SELECT id FROM texts_{language} WHERE {' AND '.join(conditions)}"
        return bool(self.db.execute(query, params))

    def find(self, language: str, **filters) -> List[Dict]:
        """Универсальный поиск"""
        table = self._get_language_table(language)
        
        if not filters:
            results = self.db.execute(f"SELECT * FROM {table}")
        else:
            conditions = [f"{k} = ?" for k in filters.keys()]
            params = list(filters.values())
            where = " AND ".join(conditions)
            results = self.db.execute(f"SELECT * FROM {table} WHERE {where}", params)
        
        return results
    
    def find_one(self, language: str, **filters) -> Optional[Dict]:
        """Найти одну запись"""
        results = self.find(language, **filters)
        return results[0] if results else None

class TableManager(BaseManager):
    def create_all(self):
        """Создает все нужные таблицы"""  
        # 1. Таблицы текстов для каждого языка (оставляем как есть)
        for lang in self.languages:
            self.db.execute(f'''
                CREATE TABLE IF NOT EXISTS texts_{lang} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    translator TEXT, 
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
                CREATE TABLE IF NOT EXISTS sent_{lang} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text_id INTEGER NOT NULL,
                    sentence TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    smell_word TEXT,
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
                CREATE INDEX IF NOT EXISTS idx_sent_{lang}_text 
                ON sent_{lang}(text_id)
            ''')
            self.db.execute(f'''
                CREATE INDEX IF NOT EXISTS idx_sent_{lang}_position 
                ON sent_{lang}(position)
            ''')
        
        # 4. Таблица выравнивания ТОЛЬКО для ольфакторных предложений
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS olfactory_alignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ru_id INTEGER NOT NULL,
                en_id INTEGER NOT NULL,
                verified BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ru_id) REFERENCES sent_ru(id) ON DELETE CASCADE,
                FOREIGN KEY (en_id) REFERENCES sent_en(id) ON DELETE CASCADE,
                UNIQUE(ru_id, en_id)
            )
        ''')
        
        for lang in self.languages:
            self.db.execute(f'''
                CREATE TABLE IF NOT EXISTS olfactory_words_{lang}(
                    id INTEGER PRIMARY KEY,
                    olf_id INTEGER NOT NULL,           -- ссылка на предложение
                    word TEXT NOT NULL,                 -- слово
                    lemma TEXT,                         -- лемма
                    pos TEXT,                           -- часть речи
                    children TEXT,
                    concept TEXT,                       -- словосочетание
                    FOREIGN KEY (olf_id) REFERENCES sent_{lang}(id) ON DELETE CASCADE
                );
            ''')
        
        print("📊 Все таблицы успешно созданы")

class TextManager(BaseManager):
    table_base_name = 'texts'
    
    def _add_text(self, language, title, author, translator, year, content, text_type):
        """Внутренний метод для добавления текста (без логики связей)"""
        table = self._get_language_table(language)
        return self.db.execute(
            f"INSERT INTO {table} (title, author, translator, year, content, text_type) VALUES (?, ?, ?, ?, ?, ?)",
            (title, author, translator, year, content, text_type)
        )
    
    def add_original(self, language, title, author, year, content):
        if self._validate_text_exists(language, title=title):
            raise ValueError(f'Текст с названием {title} уже существует')
        
        return self._add_text(language, title, author, '-', year, content, 'original')

    def add_translation(self, language, title, author, translator, year, content, original_lang, original_id):
        trans_id = self._add_text(language, title, author, translator, year, content, 'translation')
        self.db.execute(
            "INSERT INTO text_relations (original_lang, original_id, translation_lang, translation_id) VALUES (?, ?, ?, ?)",
            (original_lang, original_id, language, trans_id)
        )
        return trans_id

    def get_translations(self, original_lang, original_id):
        """Получить все переводы текста"""
        relations = self.db.execute(
            "SELECT * FROM text_relations WHERE original_lang = ? AND original_id = ?",
            (original_lang, original_id)
        )
        
        translations = []
        for rel in relations:
            table = self._get_language_table(rel['translation_lang'])
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
            table = self._get_language_table(rel['original_lang'])
            text = self.db.execute(
                f"SELECT * FROM {table} WHERE id = ?",
                (rel['original_id'],)
            )
            if text:
                text[0]['language'] = rel['original_lang']
                return text[0]
        return None

    def get_by_language(self, language, text_type=None):
        """Получить все тексты на языке"""
        table = self._get_language_table(language)
        if text_type:
            return self.db.execute(
                f"SELECT * FROM {table} WHERE text_type = ? ORDER BY author, year",
                (text_type,)
            )
        return self.db.execute(f"SELECT * FROM {table} ORDER BY author, year")
        
    def delete(self, language, text_id):
        """Удалить текст"""
        table = self._get_language_table(language)
        
        # Удаляем связи
        self.db.execute(
            "DELETE FROM text_relations WHERE (original_lang = ? AND original_id = ?) OR (translation_lang = ? AND translation_id = ?)",
            (language, text_id, language, text_id)
        )
        
        # Удаляем текст
        return self.db.execute(f"DELETE FROM {table} WHERE id = ?", (text_id,))

class OlfactoryManager(BaseManager):
    table_base_name = 'sent'
    
    def add(self, language: str, text_id: int, position: int, sentence: str,  # ← добавить position
            smell_words: list = None, left_context: str = None, 
            right_context: str = None, verified: bool = False,
            type_val: str = None, connotation: str = None, 
            tonal: str = None, gramm_structure: str = None,
            comments: str = None) -> int:
        
        table = self._get_language_table(language)
        
        if not self._validate_text_exists(language, id=text_id):
            raise ValueError(f"Текст с id {text_id} не существует")
        
        # 1. Добавляем предложение (с position!)
        cursor = self.db.conn.execute(f"""
            INSERT INTO {table} 
            (text_id, position, sentence, left_context, right_context,
            type, connotation, tonal, gramm_structure, comments, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (text_id, position, sentence, left_context, right_context,
            type_val, connotation, tonal, gramm_structure, comments, 
            1 if verified else 0))
        
        olf_id = cursor.lastrowid
        
        # 2. Добавляем слова
        if smell_words:
            word_table = f"olfactory_words_{language}"
            for i, word_data in enumerate(smell_words):
                if isinstance(word_data, str):
                    word = word_data
                    lemma = None
                    pos = None
                    children = None
                    concept = None
                else:
                    word = word_data.get('word', '')
                    lemma = word_data.get('lemma')
                    pos = word_data.get('pos')
                    children = word_data.get("children")
                    concept = word_data.get('concept')
                
                self.db.execute(f"""
                    INSERT INTO {word_table} 
                    (olf_id, word, lemma, pos, children, concept)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (olf_id, word, lemma, pos, children, concept))
        
        self.db.conn.commit()
        return olf_id
    
    def update(self, language: str, olf_id: int, **kwargs) -> bool:
        """
        Обновить поля предложения
        
        Args:
            language: язык
            olf_id: ID предложения
            **kwargs: поля для обновления
                Можно обновлять: smell_words
                type, connotation, tonal, gramm_structure, comments, verified
        """
        table = self._get_language_table(language)
        
        # Разрешенные поля для обновления
        allowed_fields = [
            'smell_words','type', 'connotation', 'tonal', 'gramm_structure', 
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
    
    def delete(self, language: str, olf_id: int) -> bool:
        """Удалить ольфакторное предложение"""
        table = self._get_language_table(language)
        return bool(self.db.execute(f"DELETE FROM {table} WHERE id = ?", (olf_id,)))

    def delete_by_text(self, language: str, text_id: int) -> bool:
        """Удалить все предложения текста"""
        table = self._get_language_table(language)
        return bool(self.db.execute(
            f"DELETE FROM {table} WHERE text_id = ?", 
            (text_id,)
        ))

class CsvExporter(BaseManager):
    
    def export_aligned_data(self, output_path: str = None, 
                        ru_text_id: int = None, 
                        en_text_id: int = None) -> Union[List[Dict], str]:
        """
        Экспортирует выровненные предложения
        Args:
            output_path: путь для сохранения CSV (если None - вернет список)
            ru_text_id: ID русского текста (опционально)
            en_text_id: ID английского текста (опционально)
        """
        import pandas as pd
        
        rows = []
        
        # Формируем запрос
        if ru_text_id and en_text_id:
            alignments = self.db.execute("""
                SELECT a.ru_id, a.en_id, a.verified as alignment_verified
                FROM olfactory_alignments a
                WHERE a.ru_id IN (SELECT id FROM sent_ru WHERE text_id = ?)
                AND a.en_id IN (SELECT id FROM sent_en WHERE text_id = ?)
                ORDER BY a.ru_id
            """, (ru_text_id, en_text_id))
        else:
            alignments = self.db.execute("""
                SELECT ru_id, en_id, verified as alignment_verified
                FROM olfactory_alignments
                ORDER BY ru_id
            """)
        
        for align in alignments:
            # Получаем русское предложение
            ru_sent = self.db.execute(
                "SELECT * FROM sent_ru WHERE id = ?",
                (align['ru_id'],)
            )
            # Получаем английское предложение
            en_sent = self.db.execute(
                "SELECT * FROM sent_en WHERE id = ?",
                (align['en_id'],)
            )
            if not ru_sent or not en_sent:
                continue
                
            ru_sent = ru_sent[0]
            en_sent = en_sent[0]
            
            # Получаем русские слова-запахи
            ru_words = self.db.execute("SELECT * FROM olfactory_words_ru WHERE olf_id = ?", (align['ru_id'],))
            # Получаем английские слова-запахи
            en_words = self.db.execute("SELECT * FROM olfactory_words_en WHERE olf_id = ?", (align['en_id'],))
            
            # Если слов нет - создаем одну строку с пустыми значениями
            if not ru_words:
                ru_words = [{'word': '', 'pos': '', 'concept': ''}]
            if not en_words:
                en_words = [{'word': '', 'pos': '', 'concept': ''}]
            
            # Берем максимальное количество слов для создания строк
            max_words = max(len(ru_words), len(en_words))
            
            for i in range(max_words):
                ru_word = ru_words[i] if i < len(ru_words) else {}
                en_word = en_words[i] if i < len(en_words) else {}
                
                row = {
                    # Русская часть
                    'ru_text_id': ru_sent.get('text_id', ''),
                    'ru_sent_id': ru_sent.get('id', ''),
                    'ru_position': ru_sent.get('position', ''),
                    'ru_sentence': ru_sent.get('sentence', '') if i == 0 else '',

                    # Русские токены
                    'ru_token': ru_word.get('word', ''),
                    'ru_token_pos': ru_word.get('pos', ''),
                    'ru_concept': ru_word.get('concept', ''),

                    # Аннотации (только для первой строки)
                    'ru_type': ru_sent.get('type', '') if i == 0 else '',
                    'ru_connotation': ru_sent.get('connotation', '') if i == 0 else '',
                    'ru_intensity': '',
                    'ru_tonality': ru_sent.get('tonal', '') if i == 0 else '',
                    'ru_gram_structure': ru_sent.get('gramm_structure', '') if i == 0 else '',
                    'ru_comments': ru_sent.get('comments', '') if i == 0 else '',
                    
                    # Английская часть
                    'en_text_id': en_sent.get('text_id', ''),
                    'en_sent_id': en_sent.get('id', ''),
                    'en_position': en_sent.get('position', ''),
                    'en_sentence': en_sent.get('sentence', '') if i == 0 else '',

                    # Английские токены
                    'en_token': en_word.get('word', ''),
                    'en_token_pos': en_word.get('pos', ''),
                    'en_concept': en_word.get('concept', ''),

                    # Аннотации (только для первой строки)
                    'en_type': en_sent.get('type', '') if i == 0 else '',
                    'en_connotation': en_sent.get('connotation', '') if i == 0 else '',
                    'en_intensity': '',
                    'en_tonality': en_sent.get('tonal', '') if i == 0 else '',
                    'en_gram_structure': en_sent.get('gramm_structure', '') if i == 0 else '',
                    'en_comments': en_sent.get('comments', '') if i == 0 else '',

                    # Метаданные
                    'translation_shift': 'aligned',
                    'cosine_sim_LaBSE': '',
                    'shift_notes': '',
                    'verified': 1 if (ru_sent.get('verified', 0) and en_sent.get('verified', 0)) else 0
                }
                rows.append(row)
        
        if output_path is None:
            return rows
        
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"✅ CSV сохранен: {output_path}")
        print(f"📊 Всего строк: {len(rows)}")
        
        return output_path

class AlignmentHelper(BaseManager):
    
    def export_for_alignment(self, ru_text_id: int, en_text_id: int, 
                            output_path: str = None,
                            only_unmatched: bool = True) -> str:
        """
        Экспортирует Excel для ручного выравнивания
        
        Args:
            ru_text_id: ID русского текста
            en_text_id: ID английского текста
            output_path: путь для сохранения
            only_unmatched: если True - только невыровненные предложения
        """
        import pandas as pd
        
        # Получаем уже существующие выравнивания
        existing_alignments = {}
        if only_unmatched:
            existing = self.db.execute("""
                SELECT ru_id, en_id 
                FROM olfactory_alignments 
                WHERE ru_id IN (SELECT id FROM sent_ru WHERE text_id = ?)
                AND en_id IN (SELECT id FROM sent_en WHERE text_id = ?)
            """, (ru_text_id, en_text_id))
            
            for a in existing:
                existing_alignments[a['ru_id']] = a['en_id']
        
        # Получаем русские предложения
        ru_sentences = self.db.execute("""
            SELECT id, sentence, position
            FROM sent_ru 
            WHERE text_id = ? 
            ORDER BY position
        """, (ru_text_id,))
        
        # Фильтруем: оставляем только невыровненные
        ru_to_align = []
        for ru in ru_sentences:
            if only_unmatched and ru['id'] in existing_alignments:
                continue  # пропускаем уже выровненные
            ru_to_align.append({
                'ru_id': ru['id'],
                'position': ru['position'],
                'ru_sentence': ru['sentence'],
                'aligned_en_id': '',  # пустое поле для заполнения
                'status': 'new'  # пометка, что это новое
            })
        
        # Получаем английские предложения (все, для справки)
        en_sentences = self.db.execute("""
            SELECT id, sentence, position
            FROM sent_en 
            WHERE text_id = ? 
            ORDER BY position
        """, (en_text_id,))
        
        en_df = pd.DataFrame([{
            'en_id': en['id'],
            'position': en['position'],
            'en_sentence': en['sentence']
        } for en in en_sentences])
        
        # Создаем DataFrame с русскими
        ru_df = pd.DataFrame(ru_to_align)
        
        # Сохраняем - ИСПРАВЛЕНО!
        if output_path is None:
            # Просто используем ID в имени файла
            output_path = f"alignment_{ru_text_id}_to_{en_text_id}.xlsx"
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            ru_df.to_excel(writer, sheet_name='Русские (невыровненные)', index=False)
            en_df.to_excel(writer, sheet_name='Английские (справочник)', index=False)
            
            # Добавляем третий лист со статистикой
            stats = pd.DataFrame([{
                'Всего русских': len(ru_sentences),
                'Уже выровнено': len(existing_alignments),
                'Осталось выровнять': len(ru_to_align),
                'Всего английских': len(en_sentences)
            }])
            stats.to_excel(writer, sheet_name='Статистика', index=False)
        
        print(f"📝 Шаблон создан: {output_path}")
        print(f"\n📊 СТАТИСТИКА:")
        print(f"   Всего русских предложений: {len(ru_sentences)}")
        print(f"   Уже выровнено: {len(existing_alignments)}")
        print(f"   Осталось выровнять: {len(ru_to_align)}")
        print(f"   Всего английских: {len(en_sentences)}")
        
        if len(ru_to_align) == 0:
            print(f"\n✅ Все предложения уже выровнены! Ничего делать не нужно.")
        
        return output_path
        
    def import_alignment_from_excel(self, excel_path: str, 
                                    ru_text_id: int = None,
                                    en_text_id: int = None,
                                    clear_existing: bool = False) -> Dict:
        """
        Импортирует выравнивания из размеченного Excel
        
        Args:
            excel_path: путь к Excel с заполненным aligned_en_id
            ru_text_id: ID русского текста (опционально, для проверки)
            en_text_id: ID английского текста (опционально, для проверки)
            clear_existing: удалить существующие выравнивания перед импортом
        """
        import pandas as pd
        
        # Читаем лист с русскими (название может быть разным)
        try:
            df = pd.read_excel(excel_path, sheet_name='Русские (невыровненные)', engine='openpyxl')
        except:
            # Если нет такого листа, пробуем старый формат
            df = pd.read_excel(excel_path, sheet_name='Русские', engine='openpyxl')
        
        # Проверяем колонки
        required_cols = ['ru_id', 'aligned_en_id']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"В Excel нет колонки {col}")
        
        # Очищаем существующие выравнивания если нужно
        if clear_existing:
            if ru_text_id and en_text_id:
                self.db.execute("""
                    DELETE FROM olfactory_alignments 
                    WHERE ru_id IN (SELECT id FROM sent_ru WHERE text_id = ?)
                    AND en_id IN (SELECT id FROM sent_en WHERE text_id = ?)
                """, (ru_text_id, en_text_id))
                print(f"🧹 Удалены старые выравнивания")
            else:
                self.db.execute("DELETE FROM olfactory_alignments")
                print(f"🧹 Удалены все выравнивания")
        
        # Собираем выравнивания
        alignments = []
        skipped = 0
        not_found = 0
        already_exists = 0
        
        for idx, row in df.iterrows():
            ru_id = row['ru_id']
            en_id = row['aligned_en_id']
            
            # Пропускаем пустые
            if pd.isna(en_id) or en_id == '':
                skipped += 1
                continue
            
            en_id = int(en_id)
            
            # Проверяем существование
            ru_exists = self.db.execute("SELECT id FROM sent_ru WHERE id = ?", (ru_id,))
            en_exists = self.db.execute("SELECT id FROM sent_en WHERE id = ?", (en_id,))
            
            if not ru_exists:
                print(f"⚠️ Русское {ru_id} не найдено")
                not_found += 1
                continue
                
            if not en_exists:
                print(f"⚠️ Английское {en_id} не найдено")
                not_found += 1
                continue
            
            # Проверяем тексты
            if ru_text_id:
                ru_text = self.db.execute("SELECT text_id FROM sent_ru WHERE id = ?", (ru_id,))
                if ru_text and ru_text[0]['text_id'] != ru_text_id:
                    print(f"⚠️ Русское {ru_id} не из текста {ru_text_id}")
                    not_found += 1
                    continue
            
            if en_text_id:
                en_text = self.db.execute("SELECT text_id FROM sent_en WHERE id = ?", (en_id,))
                if en_text and en_text[0]['text_id'] != en_text_id:
                    print(f"⚠️ Английское {en_id} не из текста {en_text_id}")
                    not_found += 1
                    continue
            
            # Проверяем, не существует ли уже это выравнивание
            if not clear_existing:
                existing = self.db.execute("""
                    SELECT id FROM olfactory_alignments 
                    WHERE ru_id = ? AND en_id = ?
                """, (ru_id, en_id))
                if existing:
                    already_exists += 1
                    continue
            
            alignments.append((ru_id, en_id))
        
        # Сохраняем в БД
        inserted = 0
        for ru_id, en_id in alignments:
            try:
                self.db.execute("""
                    INSERT OR REPLACE INTO olfactory_alignments (ru_id, en_id, verified)
                    VALUES (?, ?, ?)
                """, (ru_id, en_id, 0))
                inserted += 1
            except Exception as e:
                print(f"❌ Ошибка: {ru_id}->{en_id}: {e}")
        
        self.db.conn.commit()
        
        print(f"\n📊 РЕЗУЛЬТАТЫ ИМПОРТА:")
        print(f"   ✅ Добавлено новых: {inserted}")
        print(f"   ⏭️ Пропущено (пустые aligned_en_id): {skipped}")
        print(f"   ⚠️ Не найдено в БД: {not_found}")
        print(f"   🔄 Уже существовало: {already_exists}")
        print(f"   📝 Всего строк в Excel: {len(df)}")
        
        return {
            'inserted': inserted,
            'skipped': skipped,
            'not_found': not_found,
            'already_exists': already_exists,
            'total': len(df)
        }
        
    
