# run.py
"""
Управление проектом
Запуск:
    python run.py db              # создать БД
    python run.py migrate         # применить миграции
    python run.py backup          # бекап БД
    python run.py reset           # полный сброс
    
    python run.py ingest          # загрузить книги из CSV
    python run.py link            # связать переводы
    python run.py check           # проверить несвязанные переводы
    
    python run.py detect          # найти ольфакторные предложения (без очистки)
    python run.py detect --clear   # найти ольфакторные предложения (с очисткой)
    
    python run.py list-align
    python run.py export-align
    python run.py import-align
    
    python run.py jupyter         # запустить Jupyter
    
    python run.py sborka
"""

import sys
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

# Используем ТОТ ЖЕ Python, который запускает run.py
PYTHON = sys.executable

CURRENT_SCHEMA = 'schema_v01.sql'  # проверьте точное имя файла

def run_db():
    print("📦 Создание базы данных...")
    subprocess.run([PYTHON, "db/create_db.py", CURRENT_SCHEMA])

def run_migrate():
    print("🔄 Применение миграций...")
    subprocess.run([PYTHON, "db/migrate.py"])

def run_ingest():
    print("📚 Загрузка книг...")
    subprocess.run([PYTHON, "src/ingest.py"])

def run_link():
    print("🔗 Связывание переводов...")
    subprocess.run([PYTHON, "src/ingest.py", "--link"])

def run_check():
    print("🔍 Проверка связей...")
    subprocess.run([PYTHON, "src/ingest.py", "--check"])

def run_backup():
    print("💾 Бекап БД...")
    subprocess.run([PYTHON, "db/backup.py"])

def run_reset():
    print("🔄 Полный сброс...")
    run_backup()
    run_db()
    run_migrate()

def run_detect():
    """python run.py detect          — без очистки
       python run.py detect --clear — с очисткой"""
    
    # Проверяем, есть ли флаг --clear
    clear_flag = '--clear' in sys.argv
    
    print("🔍 Поиск ольфакторных предложений...")
    if clear_flag:
        print("   ⚠️ Режим очистки: старые данные будут удалены")
        subprocess.run([PYTHON, "src/processing.py", "--clear"])
    else:
        subprocess.run([PYTHON, "src/processing.py"])

def run_alignment_list():
    subprocess.run([PYTHON, "src/alignment.py", "--list"])

def run_alignment_export():
    """Экспорт: python run.py export-align 1 1"""
    if len(sys.argv) < 4:
        print("❌ Укажите ru_text_id и translation_id")
        print("   Пример: python run.py export-align 1 1")
        return
    ru_id = sys.argv[2]
    en_id = sys.argv[3]
    subprocess.run([PYTHON, "src/alignment.py", "--export", "--ru", ru_id, "--en", en_id])

def run_alignment_import():
    subprocess.run([PYTHON, "src/alignment.py", "--import"])


def run_auto_align():
    """
    Автовыравнивание через LaBSE.

    python run.py auto-align 1 1             — пара (ru_text_id=1, translation_id=1)
    python run.py auto-align 1 1 --threshold 0.60
    python run.py auto-align 1 1 --no-window
    python run.py auto-align 1 1 --dry-run
    python run.py auto-align 1 1 --reverse   — 2-й проход: EN→RU для непривязанных
    python run.py auto-align --all           — все пары в БД
    """
    extra = sys.argv[2:]   # всё после "auto-align"

    # Позиционные аргументы ru_id и en_id → превращаем в --ru / --en
    positional = [a for a in extra if not a.startswith("--")]
    flags      = [a for a in extra if a.startswith("--")]

    cmd = [PYTHON, "src/auto_align.py"]
    if "--all" in flags:
        cmd += ["--all"] + [f for f in flags if f != "--all"]
    elif len(positional) >= 2:
        cmd += ["--ru", positional[0], "--en", positional[1]] + flags
    else:
        cmd += extra   # передаём как есть (например, --help)

    subprocess.run(cmd)


def sborka():
    run_db()
    run_migrate()
    run_ingest()
    run_link()
    run_detect()
    
    run_alignment_list()
    ru_id = input("Введите ru_text_id (например, 1): ").strip()
    en_id = input("Введите translation_id (например, 1): ").strip()
    
    if ru_id and en_id:
        subprocess.run([PYTHON, "src/alignment.py", "--export", "--ru", ru_id, "--en", en_id])
    else:
        print("❌ Экспорт отменен: не указаны ID")

def main():
    commands = {
        "db": run_db,
        "migrate": run_migrate,
        "ingest": run_ingest,
        "link": run_link,
        "check": run_check,
        "backup": run_backup,
        "reset": run_reset,
        "detect": run_detect,
        "list-align": run_alignment_list,
        "export-align": run_alignment_export,
        "import-align": run_alignment_import,
        "auto-align": run_auto_align,

        "sborka": sborka
    }
    
    if len(sys.argv) < 2:
        print("Доступные команды:")
        for cmd in commands:
            print(f"  python run.py {cmd}")
        return
    
    cmd = sys.argv[1]
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"❌ Неизвестная команда: {cmd}")

if __name__ == "__main__":
    main()