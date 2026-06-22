"""
Загрузка книг из CSV в базу данных
Запуск: 
    python src/ingest.py                                    # загрузить всё
    python src/ingest.py --files f1.txt f2.txt             # загрузить конкретные
    python src/ingest.py --add --ru f.txt --en f.txt       # добавить пару в SCV
    python src/ingest.py --add --ru f.txt --en f.txt --meta author=Толстой title_ru="Война и мир" title_en="War and Peace"
    
    python src/ingest.py --link                             # связать переводы
    python src/ingest.py --check                            # проверить несвязанные
"""

import sys
import sqlite3
import argparse
import hashlib
import pandas as pd
from pathlib import Path
from config import DB_PATH, CSV_PATH, DATA_DIR


# ── Утилиты ──────────────────────────────────────────────────────────────────
def file_hash(path: Path) -> str:
    """Считает MD5 хэш файла"""
    return hashlib.md5(path.read_bytes()).hexdigest()


def hash_exists(cursor, h: str) -> bool:
    """Проверяет, есть ли файл с таким хэшем в БД"""
    r = cursor.execute(
        "SELECT 1 FROM texts WHERE file_hash=? UNION SELECT 1 FROM translations WHERE file_hash=?",
        (h, h)
    ).fetchone()
    return r is not None


def append_to_csv(ru_file: Path, en_file: Path, meta: dict):
    """
    Добавляет строки в metadata.csv.
    
    Поддерживаемые метаданные:
    - author: автор
    - title_ru: название оригинала (русское)
    - title_en: название перевода (английское)
    - translator: переводчик
    - year: год издания
    - genre: жанр
    - original_title: для связи (если отличается от title_ru)
    """
    df = pd.read_csv(CSV_PATH)
    if 'status' not in df.columns:
        df['status'] = ''

    def _row_exists(fname):
        return fname in df['file'].values

    # Получаем названия
    title_ru = meta.get('title_ru', meta.get('title', ru_file.stem))
    title_en = meta.get('title_en', meta.get('title', en_file.stem))
    original_title = meta.get('original_title', title_ru)  # для связи
    
    rows = []
    
    # Русский оригинал
    if not _row_exists(ru_file.name):
        rows.append({
            'file': ru_file.name,
            'lang': 'ru',
            'type': 'original',
            'author': meta.get('author', ''),
            'title': title_ru,
            'original_title': original_title,
            'translator': '',
            'original_id': '',
            'year': meta.get('year', ''),
            'genre': meta.get('genre', ''),
            'status': 'raw',
        })
    
    # Английский перевод
    if not _row_exists(en_file.name):
        rows.append({
            'file': en_file.name,
            'lang': 'en',
            'type': 'translation',
            'author': meta.get('author', ''),
            'title': title_en,
            'original_title': original_title,
            'translator': meta.get('translator', ''),
            'original_id': '',
            'year': meta.get('year', ''),
            'genre': meta.get('genre', ''),
            'status': 'raw',
        })

    if rows:
        new_df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        new_df.to_csv(CSV_PATH, index=False)
        print(f"📝 Добавлено в CSV: {[r['file'] for r in rows]}")
        print(f"   Оригинал: {title_ru}")
        print(f"   Перевод: {title_en}")
        if meta.get('author'):
            print(f"   Автор: {meta['author']}")
        if meta.get('translator'):
            print(f"   Переводчик: {meta['translator']}")
    else:
        print("ℹ️  Файлы уже есть в metadata.csv")


# ── 1. ЗАГРУЗКА КНИГ ИЗ CSV ─────────────────────────────────────────────────
def original_exists(cursor, title, author, language):
    """Проверяет, есть ли уже такой оригинал в БД"""
    cursor.execute("""
        SELECT text_id FROM texts 
        WHERE title = ? AND author = ? AND language = ?
    """, (title, author, language))
    return cursor.fetchone()


def translation_exists(cursor, title, translator, language):
    """Проверяет, есть ли уже такой перевод в БД"""
    cursor.execute("""
        SELECT translation_id FROM translations 
        WHERE title = ? AND translator = ? AND language = ?
    """, (title, translator, language))
    return cursor.fetchone()


def load_from_csv(files=None):
    """
    Загружает книги из CSV.
    - files=None → загружает всё из CSV
    - files=['file1.txt', 'file2.txt'] → загружает только указанные файлы
    """
    
    df = pd.read_csv(CSV_PATH)
    df = df.fillna('')
    
    # Если указаны конкретные файлы — фильтруем
    if files:
        df = df[df['file'].isin(files)]
        if df.empty:
            print(f"⚠️ Ни один из указанных файлов не найден в CSV")
            return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    stats = {'original_new': 0, 'original_skip': 0, 
             'translation_new': 0, 'translation_skip': 0,
             'linked_by_title': 0,
             'errors': 0}
    
    for _, row in df.iterrows():
        file_path = DATA_DIR / row['file']
        
        if not file_path.exists():
            print(f"⚠️ Файл не найден: {file_path}")
            stats['errors'] += 1
            continue
        
        # Проверка по хэшу (защита от дубликатов)
        file_hash_value = file_hash(file_path)
        if hash_exists(cursor, file_hash_value):
            print(f"⏭️ Файл уже загружен (по хэшу): {file_path.name}")
            stats['original_skip' if row['type'] == 'original' else 'translation_skip'] += 1
            continue
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if row['type'] == 'original':
            title = row['title'] if row['title'] else file_path.stem
            author = row['author'] if row['author'] else "Неизвестен"
            
            existing = original_exists(cursor, title, author, row['lang'])
            
            if existing:
                print(f"⏭️ Оригинал уже есть: {title} (id={existing[0]})")
                stats['original_skip'] += 1
                continue
            
            cursor.execute("""
                INSERT INTO texts (title, author, year, language, genre, content, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, author, row['year'] if row['year'] else None, row['lang'], 
                  row['genre'] if row['genre'] else None, content, file_hash_value))
            
            text_id = cursor.lastrowid
            print(f"✅ Новый оригинал: {title} (id={text_id})")
            stats['original_new'] += 1
            
        else:  # translation
            title = row['title'] if row['title'] else file_path.stem
            translator = row['translator'] if row['translator'] else "Неизвестен"
            
            existing = translation_exists(cursor, title, translator, row['lang'])
            
            if existing:
                print(f"⏭️ Перевод уже есть: {title} (id={existing[0]})")
                stats['translation_skip'] += 1
                continue
            
            # 1. Сначала пробуем original_id из CSV
            original_id = row['original_id'] if row['original_id'] else None
            
            # 2. Если нет original_id, пробуем найти по original_title
            if not original_id and row.get('original_title'):
                cursor.execute("""
                    SELECT text_id FROM texts 
                    WHERE title = ? AND language != ?
                """, (row['original_title'], row['lang']))
                match = cursor.fetchone()
                if match:
                    original_id = match[0]
                    print(f"   🔗 Найден оригинал по названию: {row['original_title']} (id={original_id})")
                    stats['linked_by_title'] += 1
            
            cursor.execute("""
                INSERT INTO translations (text_id, title, translator, year, language, content, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (original_id, title, translator, row['year'] if row['year'] else None, 
                  row['lang'], content, file_hash_value))
            
            translation_id = cursor.lastrowid
            
            if original_id:
                print(f"✅ Новый перевод: {title} (translation_id={translation_id}, original_id={original_id})")
            else:
                print(f"⏳ Новый перевод без связей: {title} (translation_id={translation_id})")
            
            stats['translation_new'] += 1
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*50)
    print("📊 ИТОГО:")
    print(f"   Оригиналов: +{stats['original_new']} (пропущено: {stats['original_skip']})")
    print(f"   Переводов: +{stats['translation_new']} (пропущено: {stats['translation_skip']})")
    print(f"   Из них связано по названию: {stats['linked_by_title']}")
    print(f"   Ошибок: {stats['errors']}")


# ── 2. СВЯЗЫВАНИЕ ПЕРЕВОДОВ С ОРИГИНАЛАМИ ─────────────────────────────────
def link_translations():
    """
    Связывает переводы с оригиналами по автору и названию.
    Ищет переводы, у которых text_id = NULL, и пытается найти подходящий оригинал.
    """
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Находим переводы без связей
    cursor.execute("""
        SELECT translation_id, title, translator, language 
        FROM translations 
        WHERE text_id IS NULL
    """)
    
    orphan_translations = cursor.fetchall()
    
    if not orphan_translations:
        print("✅ Нет переводов без связей")
        conn.close()
        return
    
    print(f"📋 Найдено {len(orphan_translations)} переводов без связей")
    print()
    
    linked = 0
    for trans_id, trans_title, translator, trans_lang in orphan_translations:
        
        # Определяем язык оригинала (противоположный языку перевода)
        if trans_lang == 'en':
            # Перевод на английский → ищем оригинал на русском
            cursor.execute("""
                SELECT text_id, title, author 
                FROM texts 
                WHERE language = 'ru' 
                AND (
                    title LIKE ? 
                    OR ? LIKE '%' || title || '%'
                    OR title LIKE '%' || ? || '%'
                )
                LIMIT 1
            """, (f'%{trans_title}%', trans_title, trans_title))
        else:
            # Перевод на русский → ищем оригинал на английском
            cursor.execute("""
                SELECT text_id, title, author 
                FROM texts 
                WHERE language = 'en' 
                AND (
                    title LIKE ? 
                    OR ? LIKE '%' || title || '%'
                    OR title LIKE '%' || ? || '%'
                )
                LIMIT 1
            """, (f'%{trans_title}%', trans_title, trans_title))
        
        match = cursor.fetchone()
        
        if match:
            original_id, original_title, author = match
            cursor.execute("""
                UPDATE translations 
                SET text_id = ? 
                WHERE translation_id = ?
            """, (original_id, trans_id))
            
            print(f"   ✅ Связан: '{trans_title}' → '{original_title}' (автор: {author})")
            linked += 1
        else:
            print(f"   ⚠️ Не найден оригинал для: '{trans_title}' (переводчик: {translator})")
    
    conn.commit()
    conn.close()
    
    print()
    print(f"📊 Связано переводов: {linked} из {len(orphan_translations)}")
    
    if linked < len(orphan_translations):
        print("💡 Совет: Добавьте колонку 'original_title' в CSV для точного связывания")


# ── 3. ПРОВЕРКА НЕСВЯЗАННЫХ ПЕРЕВОДОВ ─────────────────────────────────────
def check_orphans():
    """Показывает переводы, которые ещё не связаны с оригиналами"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT translation_id, title, translator, language
        FROM translations 
        WHERE text_id IS NULL
    """)
    
    orphans = cursor.fetchall()
    
    if not orphans:
        print("✅ Все переводы связаны с оригиналами")
    else:
        print(f"\n⚠️ НАЙДЕНО {len(orphans)} ПЕРЕВОДОВ БЕЗ СВЯЗЕЙ:")
        print("-" * 60)
        for trans_id, title, translator, lang in orphans:
            print(f"   ID={trans_id}, язык={lang}, title='{title}', translator='{translator}'")
        print("-" * 60)
        print("💡 Запустите 'python src/ingest.py --link' для автоматического связывания")
    
    conn.close()


# ── 4. ТОЧКА ВХОДА ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Загрузка книг из CSV в базу данных")
    
    # Режимы
    parser.add_argument('--link', action='store_true', help='Связать все переводы')
    parser.add_argument('--check', action='store_true', help='Проверить несвязанные переводы')
    parser.add_argument('--files', nargs='+', help='Загрузить только указанные файлы из CSV')
    parser.add_argument('--add', action='store_true', help='Добавить пару книг (требует --ru и --en)')
    
    # Параметры для --add
    parser.add_argument('--ru', help='Путь к русскому файлу (для --add)')
    parser.add_argument('--en', help='Путь к английскому файлу (для --add)')
    parser.add_argument('--meta', nargs='*', default=[], 
                        help='Метаданные: author="Толстой" title_ru="Война и мир" title_en="War and Peace" translator="Мод" year="1869" genre="prose"')
    
    args = parser.parse_args()
    
    # Режим --add
    if args.add:
        if not args.ru or not args.en:
            print("❌ Для --add нужны параметры --ru и --en")
            print("   Пример: python src/ingest.py --add --ru tolstoy_ru.txt --en tolstoy_en.txt --meta author=Толстой title_ru=\"Война и мир\" title_en=\"War and Peace\"")
            sys.exit(1)
        
        ru_file = Path(args.ru)
        en_file = Path(args.en)
        
        # Если пути относительные — ищем в DATA_DIR
        if not ru_file.is_absolute() and not ru_file.exists():
            ru_file = DATA_DIR / ru_file
        if not en_file.is_absolute() and not en_file.exists():
            en_file = DATA_DIR / en_file
        
        # Проверяем существование файлов
        if not ru_file.exists():
            print(f"❌ Файл не найден: {ru_file}")
            sys.exit(1)
        if not en_file.exists():
            print(f"❌ Файл не найден: {en_file}")
            sys.exit(1)
        
        # Разбираем --meta key=val
        meta = {}
        for item in args.meta:
            if '=' in item:
                k, v = item.split('=', 1)
                meta[k.strip()] = v.strip()
        
        # Добавляем в CSV и загружаем
        append_to_csv(ru_file, en_file, meta)
        load_from_csv(files=[args.ru, args.en])
        
        print("\n💡 Дальнейшие шаги:")
        print("   python src/ingest.py --link    # связать переводы")
        print("   python run.py detect           # найти ольфакторные предложения")
        print("   python run.py auto-align --all # выровнять")
    
    # Режим --link
    elif args.link:
        link_translations()
    
    # Режим --check
    elif args.check:
        check_orphans()
    
    # Режим загрузки (по умолчанию)
    else:
        load_from_csv(files=args.files)


if __name__ == "__main__":
    main()