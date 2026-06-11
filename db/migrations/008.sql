-- Миграция 008
-- Добавляет file_hash для идемпотентной загрузки книг
ALTER TABLE texts ADD COLUMN file_hash TEXT;
ALTER TABLE translations ADD COLUMN file_hash TEXT;
