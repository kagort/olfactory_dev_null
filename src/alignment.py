# src/alignment.py
"""
Экспорт и импорт для ручного выравнивания предложений.

Рабочий лист — «Английские»: каждая строка — EN-предложение,
колонка ru_№ указывает номер строки из листа «Русские».
Несколько EN-строк с одним ru_№ = одно RU разбито на части.

Запуск:
    python src/alignment.py --list
    python src/alignment.py --export --ru 1 --en 1
    python src/alignment.py --import --file results/alignment.xlsx
"""

import sys
import sqlite3
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment

from config import DB_PATH, ALIGNMENT_FILE


# ── Цвета для Excel ───────────────────────────────────────────────────────────
FILL_AUTO      = PatternFill("solid", fgColor="C6EFCE")   # зелёный      — 1-й проход (RU→EN)
FILL_SUGGESTED = PatternFill("solid", fgColor="FFEB9C")   # жёлтый       — 2-й проход (EN→RU)
FILL_MANUAL    = PatternFill("solid", fgColor="DDEBF7")   # синий         — ручное, высокий sim
FILL_MANUAL_LO = PatternFill("solid", fgColor="FFC7CE")   # красный       — ручное, низкий sim
FILL_HEADER    = PatternFill("solid", fgColor="2F5496")   # тёмно-синий   — шапка
FONT_HEADER    = Font(color="FFFFFF", bold=True)
FONT_HINT      = Font(color="888888", italic=True)

SIM_LOW_THRESHOLD = 0.70   # ниже этого порога ручное подтверждение красится красным


def get_texts_list(conn):
    """Показывает все доступные тексты и переводы."""
    print("\n📚 ДОСТУПНЫЕ ТЕКСТЫ")
    print("=" * 60)

    df_ru = pd.read_sql_query(
        "SELECT text_id, title, author FROM texts WHERE language='ru' ORDER BY title", conn)
    print("\n📖 Русские оригиналы (text_id):")
    for _, row in df_ru.iterrows():
        print(f"   {row['text_id']}: {row['title']} — {row['author']}")

    df_en = pd.read_sql_query(
        "SELECT translation_id, title, translator FROM translations WHERE language='en' ORDER BY title", conn)
    print("\n🌐 Английские переводы (translation_id):")
    for _, row in df_en.iterrows():
        print(f"   {row['translation_id']}: {row['title']} — {row['translator']}")

    return df_ru, df_en


def export_for_alignment(conn, ru_text_id, translation_id, output_path=ALIGNMENT_FILE):
    """
    Экспортирует ольфакторные предложения для проверки и разметки.

    Структура Excel:
    ┌─────────────────────────────────────────────────────────┐
    │ Лист «Русские» — СПРАВОЧНИК (не редактируется)          │
    │   №  ru_id  позиция  предложение  кол-во EN             │
    ├─────────────────────────────────────────────────────────┤
    │ Лист «Английские» — РАБОЧИЙ ЛИСТ                        │
    │   №  en_id  позиция  предложение  ru_№  sim  авто        │
    │                                   ▲                     │
    │          заполнено из alignment   │ редактируется        │
    └─────────────────────────────────────────────────────────┘

    Правило M:1: несколько EN-строк с одинаковым ru_№
                 означают, что одно RU разбито на части.
    """

    ru_title = pd.read_sql_query(
        "SELECT title FROM texts WHERE text_id=? AND language='ru'",
        conn, params=(ru_text_id,))
    if ru_title.empty:
        print(f"❌ Русский текст с ID={ru_text_id} не найден")
        return None

    en_title = pd.read_sql_query(
        "SELECT title FROM translations WHERE translation_id=? AND language='en'",
        conn, params=(translation_id,))
    if en_title.empty:
        print(f"❌ Английский перевод с ID={translation_id} не найден")
        return None

    print(f"\n📖 Экспорт:")
    print(f"   RU: {ru_title.iloc[0]['title']} (text_id={ru_text_id})")
    print(f"   EN: {en_title.iloc[0]['title']} (translation_id={translation_id})")

    # ── 1. Все ольфакторные предложения ──────────────────────────────────────
    df_ru = pd.read_sql_query(f"""
        SELECT sentence_id AS ru_id, position, sentence
        FROM sentences
        WHERE source_type='original' AND text_id={ru_text_id} AND language='ru'
        ORDER BY position
    """, conn).reset_index(drop=True)

    df_en = pd.read_sql_query(f"""
        SELECT sentence_id AS en_id, position, sentence
        FROM sentences
        WHERE source_type='translation' AND translation_id={translation_id} AND language='en'
        ORDER BY position
    """, conn).reset_index(drop=True)

    # ── 2. Существующие связи из таблицы alignment ────────────────────────────
    df_align = pd.read_sql_query(f"""
        SELECT a.sentence_ru_id AS ru_id,
               a.sentence_en_id AS en_id,
               a.cosine_sim,
               COALESCE(a.auto_aligned, 0) AS auto_aligned
        FROM alignment a
        JOIN sentences sr ON sr.sentence_id = a.sentence_ru_id
        JOIN sentences se ON se.sentence_id = a.sentence_en_id
        WHERE sr.text_id = {ru_text_id}
          AND se.translation_id = {translation_id}
    """, conn)

    # ── 3. Порядковые номера (№) ──────────────────────────────────────────────
    df_ru.insert(0, '№', range(1, len(df_ru) + 1))
    df_en.insert(0, '№', range(1, len(df_en) + 1))

    ru_id_to_num = dict(zip(df_ru['ru_id'], df_ru['№']))
    en_id_to_num = dict(zip(df_en['en_id'], df_en['№']))

    # ── 4. Сводка по RU: сколько EN уже привязано и какие именно ────────────
    en_count = df_align.groupby('ru_id')['en_id'].count().rename('кол-во EN')
    en_nums  = df_align.groupby('ru_id')['en_id'].apply(
        lambda ids: ', '.join(str(en_id_to_num[i]) for i in ids if i in en_id_to_num)
    ).rename('EN №')
    df_ru = df_ru.join(en_count, on='ru_id').join(en_nums, on='ru_id')
    df_ru['кол-во EN'] = df_ru['кол-во EN'].fillna(0).astype(int)
    df_ru['EN №']      = df_ru['EN №'].fillna('')

    # ── 5. В EN-листе: ru_№, cosine_sim, авто ────────────────────────────────
    en_info = df_align.copy()
    en_info['ru_№']  = en_info['ru_id'].map(ru_id_to_num)
    # авто: '✓' = первый проход, '?' = второй проход (требует проверки), '' = ручное
    en_info['авто']  = en_info['auto_aligned'].map(
        lambda x: '✓' if x == 1 else ('?' if x == 2 else ''))
    en_info['sim']   = en_info['cosine_sim'].map(
        lambda x: f"{x:.3f}" if pd.notna(x) else '')

    en_info_map = en_info.set_index('en_id')[['ru_№', 'sim', 'авто']]
    df_en = df_en.join(en_info_map, on='en_id')

    # Пустые ru_№ — для ручного заполнения
    df_en['ru_№'] = df_en['ru_№'].where(df_en['ru_№'].notna(), other='')

    aligned_count   = df_align.shape[0]
    unaligned_ru    = (df_ru['кол-во EN'] == 0).sum()
    unaligned_en    = df_en['ru_№'].eq('').sum()

    print(f"   RU предложений:  {len(df_ru)} (без пары: {unaligned_ru})")
    print(f"   EN предложений:  {len(df_en)} (без пары: {unaligned_en})")
    print(f"   Уже выровнено:   {aligned_count} пар")

    # ── 6. Запись в Excel ─────────────────────────────────────────────────────
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Лист «Английские» — рабочий
        df_en[['№', 'en_id', 'position', 'sentence', 'ru_№', 'sim', 'авто']].to_excel(
            writer, sheet_name='Английские', index=False)
        # Лист «Русские» — справочник
        df_ru[['№', 'ru_id', 'position', 'sentence', 'кол-во EN', 'EN №']].to_excel(
            writer, sheet_name='Русские', index=False)

    # ── 7. Форматирование ─────────────────────────────────────────────────────
    _format_workbook(output_path, df_en)

    print(f"\n✅ Сохранено: {output_path}")
    print(f"\n📝 Инструкция:")
    print(f"   1. Откройте файл. Лист «Английские» — основной рабочий лист.")
    print(f"   2. 🟢 Зелёные строки — 1-й проход (RU→EN), высокая уверенность.")
    print(f"   3. 🟡 Жёлтые строки — 2-й проход (EN→RU), требуют проверки.")
    print(f"   4. Пустые строки в колонке ru_№ — заполните вручную.")
    print(f"   5. Одно RU на несколько EN: дайте им одинаковый ru_№.")
    print(f"   6. Импорт: python src/alignment.py --import --file {output_path}")

    return output_path


def _format_workbook(path, df_en):
    """Форматирует Excel: ширина колонок, цвет строк, заморозка."""
    wb = load_workbook(path)

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        # Шапка
        for cell in ws[1]:
            cell.fill = FILL_HEADER
            cell.font = FONT_HEADER
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # Ширина колонок
        col_widths = {
            'Английские': [5, 8, 10, 80, 8, 8, 6],
            'Русские':    [5, 8, 10, 80, 10],
        }
        for i, width in enumerate(col_widths.get(sheet_name, []), 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = width

        # Заморозить первую строку и первые две колонки
        ws.freeze_panes = 'C2'

        # Покраска строк EN-листа
        if sheet_name == 'Английские':
            avto_col = df_en['авто'].fillna('')
            ru_col   = df_en['ru_№'].fillna('')

            # Зелёные: первый проход (auto_aligned=1)
            auto_rows = set(
                i + 2 for i, val in enumerate(avto_col) if val == '✓'
            )
            # Жёлтые: второй проход (auto_aligned=2)
            suggested_rows = set(
                i + 2 for i, val in enumerate(avto_col) if val == '?'
            )
            # Ручные: ru_№ заполнен, но не авто — делим на красные (низкий sim) и синие
            sim_col = df_en['sim'].fillna('')
            manual_lo_rows = set()  # красные: ручное + низкий sim
            manual_hi_rows = set()  # синие:   ручное + нормальный sim
            for i, (ru_num, avto, sim_val) in enumerate(zip(ru_col, avto_col, sim_col)):
                if ru_num != '' and avto == '':
                    try:
                        sim_f = float(sim_val)
                        if sim_f < SIM_LOW_THRESHOLD:
                            manual_lo_rows.add(i + 2)
                        else:
                            manual_hi_rows.add(i + 2)
                    except (ValueError, TypeError):
                        manual_hi_rows.add(i + 2)

            for row in ws.iter_rows(min_row=2):
                r = row[0].row
                if r in auto_rows:
                    for cell in row:
                        cell.fill = FILL_AUTO
                elif r in suggested_rows:
                    for cell in row:
                        cell.fill = FILL_SUGGESTED
                elif r in manual_lo_rows:
                    for cell in row:
                        cell.fill = FILL_MANUAL_LO
                elif r in manual_hi_rows:
                    for cell in row:
                        cell.fill = FILL_MANUAL

        # Перенос текста в колонке «предложение» (4-я колонка)
        for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')

    wb.save(path)


def import_alignment_from_excel(conn, excel_path=ALIGNMENT_FILE):
    """
    Импортирует выровненные пары из EN-листа Excel в таблицу alignment.

    Читает колонку ru_№ листа «Английские».
    Несколько EN с одинаковым ru_№ → M:1 (дробление предложения).
    """
    if not Path(excel_path).exists():
        print(f"❌ Файл не найден: {excel_path}")
        return None

    df_en  = pd.read_excel(excel_path, sheet_name='Английские', engine='openpyxl')
    df_ru  = pd.read_excel(excel_path, sheet_name='Русские',    engine='openpyxl')

    # Карта №→ru_id из справочного листа
    ru_num_to_id = dict(zip(df_ru['№'].astype(int), df_ru['ru_id'].astype(int)))

    # Фильтруем заполненные строки
    df_filled = df_en[
        df_en['ru_№'].notna() &
        (df_en['ru_№'].astype(str).str.strip() != '')
    ].copy()

    if df_filled.empty:
        print("❌ Колонка ru_№ пуста — нечего импортировать")
        return None

    print(f"\n📥 Импорт: {len(df_filled)} заполненных EN-строк")

    cursor = conn.cursor()
    stats = {'inserted': 0, 'already': 0, 'errors': 0}

    for _, row in df_filled.iterrows():
        try:
            en_id  = int(row['en_id'])
            ru_num = int(float(str(row['ru_№']).strip()))
            ru_id  = ru_num_to_id.get(ru_num)

            if ru_id is None:
                print(f"   ⚠️  ru_№={ru_num} не найден в листе «Русские»")
                stats['errors'] += 1
                continue

            cursor.execute(
                "SELECT alignment_id FROM alignment WHERE sentence_ru_id=? AND sentence_en_id=?",
                (ru_id, en_id))

            if cursor.fetchone():
                stats['already'] += 1
            else:
                cursor.execute(
                    "INSERT INTO alignment (sentence_ru_id, sentence_en_id, auto_aligned) VALUES (?,?,0)",
                    (ru_id, en_id))
                stats['inserted'] += 1

        except Exception as e:
            print(f"   ⚠️  Ошибка строки en_id={row.get('en_id')}: {e}")
            stats['errors'] += 1

    conn.commit()

    print(f"\n✅ Импорт завершён:")
    print(f"   Добавлено: {stats['inserted']}")
    print(f"   Уже было:  {stats['already']}")
    print(f"   Ошибок:    {stats['errors']}")

    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Выравнивание предложений RU↔EN')
    parser.add_argument('--list',   action='store_true', help='Показать все тексты')
    parser.add_argument('--export', action='store_true', help='Экспорт в Excel')
    parser.add_argument('--import', dest='import_mode', action='store_true', help='Импорт из Excel')
    parser.add_argument('--ru',   type=int, help='text_id русского текста')
    parser.add_argument('--en',   type=int, help='translation_id перевода')
    parser.add_argument('--file', type=str, default=str(ALIGNMENT_FILE), help='Путь к Excel')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    if args.list:
        get_texts_list(conn)
    elif args.export:
        if not args.ru or not args.en:
            print("❌ Укажите --ru и --en (см. --list)")
        else:
            export_for_alignment(conn, args.ru, args.en, args.file)
    elif args.import_mode:
        import_alignment_from_excel(conn, args.file)
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
