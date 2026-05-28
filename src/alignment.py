# src/alignment.py
"""
Экспорт и импорт для ручного выравнивания предложений
Запуск:
    python src/alignment.py --list
    python src/alignment.py --export --ru 1 --en 1
    python src/alignment.py --import --file data/alignment.xlsx
"""

import sys
import sqlite3
import pandas as pd
from pathlib import Path

# sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, ALIGNMENT_FILE


def get_texts_list(conn):
    """Показывает все доступные тексты и переводы"""
    
    print("\n📚 ДОСТУПНЫЕ ТЕКСТЫ")
    print("=" * 60)
    
    # Русские оригиналы
    df_ru = pd.read_sql_query("""
        SELECT text_id, title, author 
        FROM texts 
        WHERE language = 'ru'
        ORDER BY title
    """, conn)
    
    print("\n📖 Русские оригиналы (text_id):")
    for _, row in df_ru.iterrows():
        print(f"   {row['text_id']}: {row['title']} — {row['author']}")
    
    # Английские переводы
    df_en = pd.read_sql_query("""
        SELECT translation_id, title, translator 
        FROM translations 
        WHERE language = 'en'
        ORDER BY title
    """, conn)
    
    print("\n🌐 Английские переводы (translation_id):")
    for _, row in df_en.iterrows():
        print(f"   {row['translation_id']}: {row['title']} — {row['translator']}")
    
    return df_ru, df_en


def export_for_alignment(conn, ru_text_id, translation_id, output_path=ALIGNMENT_FILE):
    """
    Экспортирует русские и английские предложения для ручного выравнивания
    
    Args:
        conn: sqlite3 connection
        ru_text_id: ID текста в таблице texts (русский оригинал)
        translation_id: ID перевода в таблице translations (английский перевод)
        output_path: путь для сохранения Excel файла
    """
    
    # Проверяем существование
    ru_title = pd.read_sql_query(
        "SELECT title FROM texts WHERE text_id = ? AND language = 'ru'",
        conn, params=(ru_text_id,)
    )
    if ru_title.empty:
        print(f"❌ Русский текст с ID={ru_text_id} не найден")
        return None
    
    en_title = pd.read_sql_query(
        "SELECT title FROM translations WHERE translation_id = ? AND language = 'en'",
        conn, params=(translation_id,)
    )
    if en_title.empty:
        print(f"❌ Английский перевод с ID={translation_id} не найден")
        return None
    
    print(f"\n📖 Экспорт для выравнивания:")
    print(f"   Русский: {ru_title.iloc[0]['title']} (text_id={ru_text_id})")
    print(f"   Английский: {en_title.iloc[0]['title']} (translation_id={translation_id})")
    
    # Русские невыровненные предложения
    df_ru = pd.read_sql_query(f"""
        SELECT sentence_id as ru_id, position, sentence
        FROM sentences
        WHERE source_type = 'original'
        AND text_id = {ru_text_id}
        AND language = 'ru'
        AND sentence_id NOT IN (
            SELECT sentence_ru_id FROM alignment WHERE sentence_ru_id IS NOT NULL
        )
        ORDER BY position
    """, conn)
    
    # Английские ВСЕ предложения
    df_en = pd.read_sql_query(f"""
        SELECT sentence_id as en_id, position, sentence
        FROM sentences
        WHERE source_type = 'translation'
        AND translation_id = {translation_id}
        AND language = 'en'
        AND sentence_id NOT IN (
            SELECT sentence_en_id FROM alignment WHERE sentence_en_id IS NOT NULL
            )
        ORDER BY position
    """, conn)
    
    if df_ru.empty:
        print(f"   ⚠️ Нет невыровненных русских предложений")
    else:
        print(f"   Русских (невыровненных): {len(df_ru)}")
    print(f"   Английских (всего): {len(df_en)}")
    
    # Добавляем порядковые номера — чтобы не работать с глобальными sentence_id
    df_ru = df_ru.reset_index(drop=True)
    df_ru.insert(0, '№', range(1, len(df_ru) + 1))
    df_ru['aligned_en_№'] = ''

    df_en = df_en.reset_index(drop=True)
    df_en.insert(0, '№', range(1, len(df_en) + 1))

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_ru[['№', 'ru_id', 'position', 'sentence', 'aligned_en_№']].to_excel(
            writer, sheet_name='Русские', index=False)
        df_en[['№', 'en_id', 'position', 'sentence']].to_excel(
            writer, sheet_name='Английские', index=False)

    print(f"\n✅ Экспортировано в {output_path}")
    print(f"\n📝 Инструкция:")
    print(f"   1. Откройте файл в Excel")
    print(f"   2. На листе 'Английские' найдите нужное предложение по колонке '№'")
    print(f"   3. На листе 'Русские' заполните колонку 'aligned_en_№' (порядковый номер из EN-листа)")
    print(f"   4. Сохраните файл")
    print(f"   5. Запустите импорт: python src/alignment.py --import --file {output_path}")
    
    return output_path


def import_alignment_from_excel(conn, excel_path=ALIGNMENT_FILE):
    """
    Импортирует выровненные пары из Excel в таблицу alignment
    
    Args:
        conn: sqlite3 connection
        excel_path: путь к Excel файлу
    """
    
    if not Path(excel_path).exists():
        print(f"❌ Файл не найден: {excel_path}")
        return None
    
    df_ru_sheet = pd.read_excel(excel_path, sheet_name='Русские', engine='openpyxl')

    # Поддерживаем оба формата: новый (aligned_en_№) и старый (aligned_en_id)
    use_seq = 'aligned_en_№' in df_ru_sheet.columns
    fill_col = 'aligned_en_№' if use_seq else 'aligned_en_id'

    en_num_to_id = {}
    if use_seq:
        df_en_sheet = pd.read_excel(excel_path, sheet_name='Английские', engine='openpyxl')
        en_num_to_id = dict(zip(df_en_sheet['№'].astype(int), df_en_sheet['en_id'].astype(int)))

    df = df_ru_sheet
    df_filled = df[
        df[fill_col].notna() &
        (df[fill_col] != '') &
        (df[fill_col].astype(str).str.strip() != '')
    ]

    if df_filled.empty:
        print(f"❌ Нет заполненных пар (колонка '{fill_col}' пуста)")
        return None

    print(f"\n📥 Импорт выровненных пар...")
    print(f"   Найдено заполненных строк: {len(df_filled)}")

    cursor = conn.cursor()
    stats = {'inserted': 0, 'already': 0, 'errors': 0}

    for _, row in df_filled.iterrows():
        try:
            ru_id = int(row['ru_id'])
            if use_seq:
                en_num = int(row['aligned_en_№'])
                en_id = en_num_to_id.get(en_num)
                if en_id is None:
                    print(f"   ⚠️ № {en_num} не найден в листе «Английские»")
                    stats['errors'] += 1
                    continue
            else:
                en_id = int(row['aligned_en_id'])
            
            # Проверяем, существует ли уже
            cursor.execute("""
                SELECT alignment_id FROM alignment 
                WHERE sentence_ru_id = ? AND sentence_en_id = ?
            """, (ru_id, en_id))
            
            if cursor.fetchone():
                stats['already'] += 1
            else:
                cursor.execute("""
                    INSERT INTO alignment (sentence_ru_id, sentence_en_id)
                    VALUES (?, ?)
                """, (ru_id, en_id))
                stats['inserted'] += 1
                
        except Exception as e:
            print(f"   ⚠️ Ошибка для ru_id={row.get('ru_id')}: {e}")
            stats['errors'] += 1
    
    conn.commit()
    
    print(f"\n✅ Импорт завершён:")
    print(f"   Добавлено новых: {stats['inserted']}")
    print(f"   Уже существовали: {stats['already']}")
    print(f"   Ошибок: {stats['errors']}")
    
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Ручное выравнивание предложений')
    parser.add_argument('--list', action='store_true', help='Показать все тексты')
    parser.add_argument('--export', action='store_true', help='Экспорт для выравнивания')
    parser.add_argument('--import', dest='import_mode', action='store_true', help='Импорт из Excel')
    parser.add_argument('--ru', type=int, help='ID русского текста (text_id)')
    parser.add_argument('--en', type=int, help='ID английского перевода (translation_id)')
    parser.add_argument('--file', type=str, default='results/alignment.xlsx', help='Путь к Excel файлу')

    args = parser.parse_args()
    
    conn = sqlite3.connect(DB_PATH)
    
    if args.list:
        get_texts_list(conn)
    
    elif args.export:
        if not args.ru or not args.en:
            print("❌ Укажите --ru и --en")
            print("   Предварительно запустите --list, чтобы узнать ID")
        else:
            export_for_alignment(conn, args.ru, args.en, args.file)
    
    elif args.import_mode:
        import_alignment_from_excel(conn, args.file)
    
    else:
        parser.print_help()
    
    conn.close()


if __name__ == "__main__":
    main()