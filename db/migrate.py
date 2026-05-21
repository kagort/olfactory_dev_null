# db/migrate.py
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "olfactory.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def migrate():
    if not DB_PATH.exists():
        print("❌ База данных не существует. Запустите: make db")
        return
    
    conn = sqlite3.connect(DB_PATH)
    
    # Таблица для отслеживания примененных миграций
    conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP
        )
    """)
    
    # Какие миграции уже применены?
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM migrations")
    applied = {row[0] for row in cursor.fetchall()}
    
    # Все файлы миграций по порядку
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    
    # Применяем новые
    for filepath in migration_files:
        if filepath.name in applied:
            continue
        
        print(f"  → {filepath.name}")
        with open(filepath, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO migrations (name, applied_at) VALUES (?, ?)",
            (filepath.name, datetime.now())
        )
        conn.commit()
    
    conn.close()
    print("✅ Миграции применены")

if __name__ == "__main__":
    migrate()