# Makefile
# ВСЕ ВЕРСИИ ЗАДАНЫ В ОДНОМ МЕСТЕ - ЗДЕСЬ

CURRENT_SCHEMA = shema_v01.sql   # <<-- МЕНЯЙТЕ ЗДЕСЬ ПРИ ОБНОВЛЕНИИ

.PHONY: help db migrate backup reset parse add-book

db:
	@python db/create_db.py $(CURRENT_SCHEMA)

migrate:
	@python db/migrate.py

backup:
	@python db/backup.py

reset: backup
	@rm -f db/olfactory.db
	@$(MAKE) db
	@$(MAKE) migrate

# Добавление файлов

ingest:
	@echo "📚 Загрузка книг из CSV..."
	@python src/ingest.py

link:
	@echo "🔗 Связывание переводов с оригиналами..."
	@python src/ingest.py --link

check-orphans:
	@python src/ingest.py --check

parse:
	@echo "🔍 UD-парсинг концептов (gram_structure)..."
	@python src/processing.py --parse-only

add-book:
	@echo "📚 Добавление книги..."
	@python run.py add-book $(ARGS)

status:
	@sqlite3 db/olfactory.db "SELECT name, applied_at FROM migrations;"
