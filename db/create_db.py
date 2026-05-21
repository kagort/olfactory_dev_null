# db/create_db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "olfactory.db"

def create_database(schema_file):
    """Создает БД из указанного файла схемы"""
    schema_path = Path(__file__).parent / "schemas" / schema_file
    
    if not schema_path.exists():
        print(f"❌ Файл не найден: {schema_path}")
        return False
    
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(sql)
    conn.close()
    
    print(f"✅ БД создана из {schema_file}")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        create_database(sys.argv[1])
    else:
        print("Укажите файл схемы: python create_db.py v003_current.sql")