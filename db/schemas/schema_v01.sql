-- schema.sql
-- Версия 1.0
-- Создано: 2026-05-12
-- Описание: Схема базы данных для ольфакторного корпуса

-- 1. Таблица текстов (исходные произведения)
CREATE TABLE IF NOT EXISTS texts (
    text_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    year INTEGER,
    language TEXT NOT NULL,
    genre TEXT,
    source TEXT,
    translation TEXT,
    content TEXT

);

-- 2. Таблица переводов
CREATE TABLE IF NOT EXISTS translations (
    translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_id INTEGER,
    title TEXT,
    translator TEXT,
    year INTEGER,
    language TEXT NOT NULL,
    content TEXT,
    FOREIGN KEY (text_id) REFERENCES texts(text_id)
);

CREATE TABLE IF NOT EXISTS sentences (
    sentence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,   -- 'original' или 'translation'
    
    -- Две колонки, но заполнена ТОЛЬКО ОДНА
    text_id INTEGER,             -- если source_type = 'original'
    translation_id INTEGER,      -- если source_type = 'translation'
    
    language TEXT NOT NULL,
    position INTEGER NOT NULL,
    sentence TEXT NOT NULL,
    
    -- разметка
    search_word TEXT,
    left_context TEXT,
    right_context TEXT,
    concept_phrase TEXT,
    syntax_tree TEXT,
    pos_tags TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Гарантия: заполнена ровно одна из двух колонок
    CHECK (
        (source_type = 'original' AND text_id IS NOT NULL AND translation_id IS NULL) OR
        (source_type = 'translation' AND translation_id IS NOT NULL AND text_id IS NULL)
    ),
    
    -- Внешние ключи
    FOREIGN KEY (text_id) REFERENCES texts(text_id) ON DELETE CASCADE,
    FOREIGN KEY (translation_id) REFERENCES translations(translation_id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS alignment (
    alignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_ru_id INTEGER NOT NULL,
    sentence_en_id INTEGER NOT NULL,
    notes TEXT,                  -- ваши комментарии
    verified BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sentence_ru_id) REFERENCES sentences(sentence_id),
    FOREIGN KEY (sentence_en_id) REFERENCES sentences(sentence_id)
);


-- 6. Русские леммы
CREATE TABLE IF NOT EXISTS lemmas_ru (
    lemma_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    pos TEXT,
    frequency INTEGER DEFAULT 0,
    semantics TEXT
);

-- 7. Английские леммы
CREATE TABLE IF NOT EXISTS lemmas_en (
    lemma_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    pos TEXT,
    frequency INTEGER DEFAULT 0,
    semantics TEXT
);

-- 8. Связь русских и английских лемм
CREATE TABLE IF NOT EXISTS lemma_mapping (
    lemma_ru_id INTEGER NOT NULL,
    lemma_en_id INTEGER NOT NULL,
    translation_shift TEXT,
    frequency INTEGER DEFAULT 1,
    PRIMARY KEY (lemma_ru_id, lemma_en_id),
    FOREIGN KEY (lemma_ru_id) REFERENCES lemmas_ru(lemma_id),
    FOREIGN KEY (lemma_en_id) REFERENCES lemmas_en(lemma_id)
);
