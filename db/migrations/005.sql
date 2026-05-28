-- Миграция 005
-- Добавляет поля для автоматического выравнивания через трансформер
ALTER TABLE alignment ADD COLUMN cosine_sim REAL;
ALTER TABLE alignment ADD COLUMN auto_aligned INTEGER DEFAULT 0;
-- auto_aligned: 0 = ручная разметка, 1 = автоматически через LaBSE
