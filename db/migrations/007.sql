-- Миграция 007
-- Добавляет колонку gram_json для структурированного хранения синтаксических признаков.
-- gram_structure остаётся как fallback на один релиз.
ALTER TABLE sentences ADD COLUMN gram_json TEXT;
