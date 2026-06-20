"""
Управление проектом — единая точка входа для всех операций.

Запуск:
    # База данных
    python run.py db              # создать БД
    python run.py migrate         # применить миграции
    python run.py backup          # бекап БД
    python run.py reset           # полный сброс
    
    # Загрузка данных
    python run.py ingest          # загрузить книги из CSV
    python run.py link            # связать переводы
    python run.py check           # проверить несвязанные переводы
    
    # Обработка предложений
    python run.py detect          # найти ольфакторные предложения
    python run.py detect --clear  # найти ольфакторные предложения (с очисткой)
    python run.py detect --text 1 # только для текста 1
    python run.py detect --parse-only  # только пересчитать грамматику
    python run.py detect --parse-only --force  # принудительно все
    python run.py detect --parse-only --sentence 42  # конкретное предложение
    
    # Выравнивание
    python run.py auto-align 1 1              # выровнять пару (ru=1, en=1)
    python run.py auto-align 1 1 --reverse    # второй проход EN->RU
    python run.py auto-align --all            # все пары в БД
    python run.py auto-align --all --reverse  # второй проход для всех
    
    # Ручная разметка
    python run.py review --ru 1 --en 1        # ручная разметка (гибридная)
    python run.py review --ru 1 --en 1 --top 5  # топ-5 кандидатов
    python run.py review --ru 1 --en 1 --parse  # с парсингом грамматики
    python run.py review --ru 1 --en 1 --weight 0.7  # больше семантики
    
    # Excel-выравнивание
    python run.py list-align                  # показать доступные пары
    python run.py export-align 1 1            # экспорт в Excel
    python run.py export-align --all          # экспорт всех пар
    python run.py import-align                # импорт из Excel
    
    # Утилиты
    python run.py jupyter                     # запустить Jupyter
    python run.py sborka                      # полная сборка (интерактивно)
    python run.py clean                       # очистка временных файлов
"""

import sys
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

# Используем ТОТ ЖЕ Python, который запускает run.py
PYTHON = sys.executable

CURRENT_SCHEMA = 'schema_v01.sql'


# ── База данных ──────────────────────────────────────────────────────────────

def run_db():
    """Создание базы данных."""
    print("📦 Создание базы данных...")
    subprocess.run([PYTHON, "db/create_db.py", CURRENT_SCHEMA])


def run_migrate():
    """Применение миграций."""
    print("🔄 Применение миграций...")
    subprocess.run([PYTHON, "db/migrate.py"])


def run_backup():
    """Бекап базы данных."""
    print("💾 Бекап БД...")
    subprocess.run([PYTHON, "db/backup.py"])


def run_reset():
    """Полный сброс (бекап + пересоздание)."""
    print("🔄 Полный сброс...")
    run_backup()
    run_db()
    run_migrate()


def run_clean():
    """Очистка временных файлов."""
    print("🧹 Очистка временных файлов...")
    import shutil
    for pattern in ["*.pyc", "__pycache__", ".pytest_cache", "*.log"]:
        for path in PROJECT_ROOT.glob(f"**/{pattern}"):
            if path.is_file():
                path.unlink()
                print(f"   Удалён: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"   Удалена папка: {path}")
    print("✅ Очистка завершена")


# ── Загрузка данных ──────────────────────────────────────────────────────────

def run_ingest():
    """Загрузка книг из CSV."""
    print("📚 Загрузка книг...")
    subprocess.run([PYTHON, "src/ingest.py"])


def run_link():
    """Связывание переводов."""
    print("🔗 Связывание переводов...")
    subprocess.run([PYTHON, "src/ingest.py", "--link"])


def run_check():
    """Проверка несвязанных переводов."""
    print("🔍 Проверка связей...")
    subprocess.run([PYTHON, "src/ingest.py", "--check"])


# ── Обработка предложений ────────────────────────────────────────────────────

def run_detect():
    """
    Поиск и разбор ольфакторных предложений.
    
    python run.py detect                    # обычный поиск
    python run.py detect --clear            # с очисткой
    python run.py detect --text 1           # только текст 1
    python run.py detect --translation 2    # только перевод 2
    
    # Режим пересчёта грамматики
    python run.py detect --parse-only       # пересчитать пустые поля
    python run.py detect --parse-only --force  # пересчитать все
    python run.py detect --parse-only --sentence 42  # конкретное предложение
    python run.py detect --parse-only --limit 100  # ограничить
    python run.py detect --parse-only --lang ru  # только русские
    """
    extra = sys.argv[2:]
    
    # Проверяем, есть ли --parse-only
    if '--parse-only' in extra:
        cmd = [PYTHON, "src/processing.py", "--parse-only"]
        # Добавляем остальные флаги, исключая --parse-only
        for flag in extra:
            if flag != '--parse-only':
                cmd.append(flag)
        subprocess.run(cmd)
    else:
        # Обычный режим detect
        cmd = [PYTHON, "src/processing.py"] + extra
        subprocess.run(cmd)


# ── Автоматическое выравнивание ─────────────────────────────────────────────

def run_auto_align():
    """
    Автовыравнивание через LaBSE.
    
    python run.py auto-align 1 1              # пара (ru=1, en=1)
    python run.py auto-align 1 1 --threshold 0.60
    python run.py auto-align 1 1 --no-window
    python run.py auto-align 1 1 --dry-run
    python run.py auto-align 1 1 --reverse    # 2-й проход EN→RU
    python run.py auto-align --all            # все пары
    python run.py auto-align --all --reverse  # 2-й проход для всех
    """
    extra = sys.argv[2:]
    
    # Позиционные аргументы ru_id и en_id → превращаем в --ru / --en
    positional = [a for a in extra if not a.startswith("--")]
    flags = [a for a in extra if a.startswith("--")]
    
    cmd = [PYTHON, "src/align_auto.py.py"]
    
    if "--all" in flags:
        cmd += ["--all"] + [f for f in flags if f != "--all"]
    elif len(positional) >= 2:
        cmd += ["--ru", positional[0], "--en", positional[1]] + flags
    else:
        cmd += extra  # передаём как есть (например, --help)
    
    subprocess.run(cmd)


# ── Ручная разметка ──────────────────────────────────────────────────────────

def run_review():
    """
    Интерактивная ручная разметка (гибридная версия v2).
    
    python run.py review --ru 1 --en 1              # стандартный режим
    python run.py review --ru 1 --en 1 --top 5      # топ-5 кандидатов
    python run.py review --ru 1 --en 1 --parse      # с парсингом грамматики
    python run.py review --ru 1 --en 1 --weight 0.7 # больше семантики
    """
    extra = sys.argv[2:]
    cmd = [PYTHON, "src/align_review.py"] + extra
    subprocess.run(cmd)


# ── Excel-выравнивание ──────────────────────────────────────────────────────

def run_alignment_list():
    """Показать доступные пары текст-перевод."""
    subprocess.run([PYTHON, "src/alignment.py", "--list"])


def run_alignment_export():
    """
    Экспорт в Excel для ручной разметки.
    
    python run.py export-align 1 1           # конкретная пара
    python run.py export-align --all         # все пары
    """
    extra = sys.argv[2:]
    
    if "--all" in extra:
        # Экспорт всех пар
        import sqlite3
        from src.config import DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        pairs = conn.execute("""
            SELECT DISTINCT t.text_id, tr.translation_id
            FROM texts t
            JOIN translations tr ON tr.text_id = t.text_id
            WHERE t.language = 'ru' AND tr.language = 'en'
            ORDER BY t.text_id, tr.translation_id
        """).fetchall()
        conn.close()
        
        if not pairs:
            print("❌ Нет пар для экспорта")
            return
        
        print(f"📤 Экспорт {len(pairs)} пар...")
        for ru_id, en_id in pairs:
            print(f"\n  Экспорт: ru={ru_id}, en={en_id}")
            subprocess.run([
                PYTHON, "src/alignment.py", 
                "--export", "--ru", str(ru_id), "--en", str(en_id)
            ])
    else:
        # Экспорт конкретной пары
        if len(extra) < 2:
            print("❌ Укажите ru_text_id и translation_id")
            print("   Пример: python run.py export-align 1 1")
            print("   Или:    python run.py export-align --all")
            return
        ru_id = extra[0]
        en_id = extra[1]
        subprocess.run([
            PYTHON, "src/alignment.py", 
            "--export", "--ru", ru_id, "--en", en_id
        ])


def run_alignment_import():
    """Импорт из Excel после ручной разметки."""
    extra = sys.argv[2:]
    cmd = [PYTHON, "src/alignment.py", "--import"] + extra
    subprocess.run(cmd)


# ── Утилиты ──────────────────────────────────────────────────────────────────

def run_jupyter():
    """Запустить Jupyter Notebook."""
    print("🚀 Запуск Jupyter...")
    subprocess.run([PYTHON, "-m", "jupyter", "notebook"])


# ── Полная сборка ────────────────────────────────────────────────────────────

def sborka():
    """Полная сборка проекта (интерактивный режим)."""
    print("\n" + "="*60)
    print("🚀 ПОЛНАЯ СБОРКА ПРОЕКТА")
    print("="*60)
    
    # 1. База данных
    print("\n[1/6] Создание БД...")
    run_db()
    run_migrate()
    
    # 2. Загрузка данных
    print("\n[2/6] Загрузка книг...")
    run_ingest()
    run_link()
    
    # 3. Поиск ольфакторных предложений
    print("\n[3/6] Поиск ольфакторных предложений...")
    subprocess.run([PYTHON, "src/processing.py"])
    
    # 4. Автовыравнивание
    print("\n[4/6] Автоматическое выравнивание...")
    subprocess.run([PYTHON, "src/auto_align.py", "--all"])
    
    # 5. Второй проход
    print("\n[5/6] Второй проход (EN→RU)...")
    subprocess.run([PYTHON, "src/auto_align.py", "--all", "--reverse"])
    
    # 6. Экспорт в Excel
    print("\n[6/6] Экспорт в Excel...")
    import sqlite3
    from src.config import DB_PATH
    
    conn = sqlite3.connect(DB_PATH)
    pairs = conn.execute("""
        SELECT DISTINCT t.text_id, tr.translation_id
        FROM texts t
        JOIN translations tr ON tr.text_id = t.text_id
        WHERE t.language = 'ru' AND tr.language = 'en'
        ORDER BY t.text_id, tr.translation_id
    """).fetchall()
    conn.close()
    
    if pairs:
        print(f"\n📤 Экспорт {len(pairs)} пар...")
        for ru_id, en_id in pairs:
            print(f"\n  Экспорт: ru={ru_id}, en={en_id}")
            subprocess.run([
                PYTHON, "src/alignment.py", 
                "--export", "--ru", str(ru_id), "--en", str(en_id)
            ])
    
    print("\n" + "="*60)
    print("✅ СБОРКА ЗАВЕРШЕНА!")
    print("="*60)
    print("\n📝 Дальнейшие шаги:")
    print("  1. Проверьте Excel-файлы в папке results/")
    print("  2. Внесите правки в колонку ru_№")
    print("  3. Импортируйте: python run.py import-align")
    print("  4. Доработайте сложные случаи: python run.py review --ru X --en Y")


# ── Главная функция ──────────────────────────────────────────────────────────

def main():
    commands = {
        # База данных
        "db": run_db,
        "migrate": run_migrate,
        "backup": run_backup,
        "reset": run_reset,
        "clean": run_clean,
        
        # Загрузка данных
        "ingest": run_ingest,
        "link": run_link,
        "check": run_check,
        
        # Обработка предложений
        "detect": run_detect,
        
        # Выравнивание
        "auto-align": run_auto_align,
        
        # Ручная разметка
        "review": run_review,
        
        # Excel-выравнивание
        "list-align": run_alignment_list,
        "export-align": run_alignment_export,
        "import-align": run_alignment_import,
        
        # Утилиты
        "jupyter": run_jupyter,
        
        # Сборка
        "sborka": sborka,
    }
    
    if len(sys.argv) < 2:
        print("📚 ДОСТУПНЫЕ КОМАНДЫ")
        print("="*60)
        print("\n📦 База данных:")
        print("  python run.py db          — создать БД")
        print("  python run.py migrate     — применить миграции")
        print("  python run.py backup      — бекап БД")
        print("  python run.py reset       — полный сброс")
        print("  python run.py clean       — очистка временных файлов")
        
        print("\n📚 Загрузка данных:")
        print("  python run.py ingest      — загрузить книги из CSV")
        print("  python run.py link        — связать переводы")
        print("  python run.py check       — проверить несвязанные переводы")
        print("  python run.py add-book    — добавить книгу из файлов")
        
        print("\n🔍 Обработка предложений:")
        print("  python run.py detect      — найти ольфакторные предложения")
        print("  python run.py detect --parse-only — пересчитать грамматику")
        
        print("\n🔗 Выравнивание:")
        print("  python run.py auto-align  — автоматическое выравнивание")
        print("  python run.py review      — ручная разметка (интерактивная)")
        print("  python run.py list-align  — показать доступные пары")
        print("  python run.py export-align — экспорт в Excel")
        print("  python run.py import-align — импорт из Excel")
        
        print("\n🚀 Сборка:")
        print("  python run.py sborka      — полная сборка проекта")
        print("  python run.py jupyter     — запустить Jupyter")
        return
    
    cmd = sys.argv[1]
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"❌ Неизвестная команда: {cmd}")
        print(f"   Используйте 'python run.py' без аргументов для списка команд")


if __name__ == "__main__":
    main()