# src/ingest.py
"""
Загрузка книг из CSV в базу данных
Запуск: 
    python src/ingest.py              # загрузить новые книги
    python src/ingest.py --link       # связать переводы с оригиналами
    python src/ingest.py --check      # проверить несвязанные переводы
"""

import sqlite3
import pandas as pd
from pathlib import Path
from config import DB_PATH, CSV_PATH, DATA_DIR

# Пути
# DB_PATH = Path(__file__).parent.parent / "db" / "olfactory.db"
# CSV_PATH = Path(__file__).parent.parent / "data" / "metadata.csv"
# DATA_DIR = Path(__file__).parent.parent / "data" / "books" / "raw"


# ============================================================
# 1. ЗАГРУЗКА НОВЫХ КНИГ ИЗ CSV
# ============================================================

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


def load_from_csv():
    """Загружает ТОЛЬКО новые записи из CSV"""
    
    df = pd.read_csv(CSV_PATH)
    df = df.fillna('')
    
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
                INSERT INTO texts (title, author, year, language, genre, content)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, author, row['year'] if row['year'] else None, row['lang'], 
                  row['genre'] if row['genre'] else None, content))
            
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
                INSERT INTO translations (text_id, title, translator, year, language, content)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (original_id, title, translator, row['year'] if row['year'] else None, row['lang'], content))
            
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

# ============================================================
# 2. СВЯЗЫВАНИЕ ПЕРЕВОДОВ С ОРИГИНАЛАМИ
# ============================================================

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


# ============================================================
# 3. ПРОВЕРКА НЕСВЯЗАННЫХ ПЕРЕВОДОВ
# ============================================================

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
        print("   Или добавьте original_id в CSV и загрузите заново")
    
    conn.close()


# ============================================================
# 4. ТОЧКА ВХОДА
# ============================================================

# src/ingest.py (с argparse)

import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--link', action='store_true', help='Связать переводы')
    parser.add_argument('--check', action='store_true', help='Проверить несвязанные')
    args = parser.parse_args()
    
    if args.link:
        link_translations()
    elif args.check:
        check_orphans()
    else:
        load_from_csv()

if __name__ == "__main__":
    main()