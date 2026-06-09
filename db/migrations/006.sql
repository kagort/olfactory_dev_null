-- Миграция 006
-- Добавляет колонку gram_structure в таблицу sentences для хранения UD-разбора
ALTER TABLE sentences ADD COLUMN gram_structure TEXT;
