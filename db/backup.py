# db/backup.py
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "olfactory.db"
BACKUP_DIR = Path(__file__).parent / "backups"

def backup():
    """Создает бекап базы данных"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    if not DB_PATH.exists():
        print(f"❌ База данных не существует: {DB_PATH}")
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f"olfactory_{timestamp}.db"
    
    shutil.copy2(DB_PATH, backup_path)
    
    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"✅ Бекап создан: {backup_path.name} ({size_mb:.2f} MB)")

def restore(backup_name):
    """Восстанавливает базу из бекапа"""
    backup_path = BACKUP_DIR / backup_name
    
    if not backup_path.exists():
        print(f"❌ Бекап не найден: {backup_path}")
        print(f"   Доступные бекапы в папке: {BACKUP_DIR}")
        return
    
    # Бекап текущей БД перед восстановлением
    if DB_PATH.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_backup = BACKUP_DIR / f"before_restore_{timestamp}.db"
        shutil.copy2(DB_PATH, temp_backup)
        print(f"📦 Текущая БД сохранена как: {temp_backup.name}")
    
    shutil.copy2(backup_path, DB_PATH)
    print(f"✅ База восстановлена из: {backup_name}")

def list_backups():
    """Показывает список бекапов"""
    backups = sorted(BACKUP_DIR.glob("olfactory_*.db"), reverse=True)
    
    if not backups:
        print("📁 Нет бекапов")
        return
    
    print("\n📋 Доступные бекапы:")
    for b in backups:
        size_mb = b.stat().st_size / (1024 * 1024)
        print(f"   {b.name} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1:
        backup()
    elif len(sys.argv) == 2 and sys.argv[1] == "list":
        list_backups()
    elif len(sys.argv) == 3 and sys.argv[1] == "restore":
        restore(sys.argv[2])
    else:
        print("Использование:")
        print("  python backup.py              # создать бекап")
        print("  python backup.py list         # список бекапов")
        print("  python backup.py restore имя.db  # восстановить")