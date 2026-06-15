# src/add_book.py
"""
Инкрементное добавление пары книг (оригинал + перевод) с полным пайплайном.

Запуск:
    python src/add_book.py --ru FILE --en FILE [--meta key=val ...]
    python src/add_book.py --ru tolstoy_ru.txt --en tolstoy_en.txt \\
        --meta author=Толстой title="Война и мир" year=1869

Цикл: append CSV → ingest → link → detect → auto-align → статистика
Идемпотентность: повторный запуск пропускает файлы с тем же hash.
"""

import sys
import sqlite3
import hashlib
import argparse
import json
from pathlib import Path

from config import DB_PATH, CSV_PATH, DATA_DIR
from ingest import load_from_csv, link_translations
from processing import process_all_texts


# ── Утилиты ──────────────────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def hash_exists(cursor, h: str) -> bool:
    r = cursor.execute(
        "SELECT 1 FROM texts WHERE file_hash=? UNION SELECT 1 FROM translations WHERE file_hash=?",
        (h, h)
    ).fetchone()
    return r is not None


def update_csv_status(file_name: str, status: str):
    """Обновляет поле status для строки с данным file в metadata.csv."""
    import pandas as pd
    df = pd.read_csv(CSV_PATH)
    if 'status' not in df.columns:
        df['status'] = ''
    df.loc[df['file'] == file_name, 'status'] = status
    df.to_csv(CSV_PATH, index=False)


def append_to_csv(ru_file: Path, en_file: Path, meta: dict):
    """Добавляет строки в metadata.csv, если файлы там ещё не упомянуты."""
    import pandas as pd
    df = pd.read_csv(CSV_PATH)
    if 'status' not in df.columns:
        df['status'] = ''

    def _row_exists(fname):
        return fname in df['file'].values

    rows = []
    if not _row_exists(ru_file.name):
        rows.append({
            'file': ru_file.name,
            'lang': 'ru',
            'type': 'original',
            'author': meta.get('author', ''),
            'title': meta.get('title', ru_file.stem),
            'original_title': meta.get('title', ru_file.stem),
            'translator': '',
            'original_id': '',
            'year': meta.get('year', ''),
            'genre': meta.get('genre', ''),
            'status': 'raw',
        })
    if not _row_exists(en_file.name):
        rows.append({
            'file': en_file.name,
            'lang': 'en',
            'type': 'translation',
            'author': meta.get('author', ''),
            'title': meta.get('title', en_file.stem),
            'original_title': meta.get('title', ru_file.stem),
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
    else:
        print("ℹ️  Файлы уже есть в metadata.csv")


def get_pair_ids(ru_file: Path, en_file: Path):
    """Возвращает (text_id, translation_id) после ingest."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    ru_hash = file_hash(ru_file)
    en_hash = file_hash(en_file)

    row = cursor.execute(
        "SELECT text_id FROM texts WHERE file_hash=?", (ru_hash,)
    ).fetchone()
    text_id = row[0] if row else None

    row = cursor.execute(
        "SELECT translation_id FROM translations WHERE file_hash=?", (en_hash,)
    ).fetchone()
    translation_id = row[0] if row else None

    conn.close()
    return text_id, translation_id


def set_file_hashes(ru_file: Path, en_file: Path):
    """После ingest записывает hash в БД, найдя записи по названию."""
    import pandas as pd
    df = pd.read_csv(CSV_PATH).fillna('')

    ru_row = df[df['file'] == ru_file.name]
    en_row = df[df['file'] == en_file.name]

    title = ru_row.iloc[0]['title'] if len(ru_row) else ru_file.stem
    author = ru_row.iloc[0]['author'] if len(ru_row) else ''
    translator = en_row.iloc[0]['translator'] if len(en_row) else ''

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE texts SET file_hash=? WHERE title=? AND author=? AND language='ru'",
        (file_hash(ru_file), title, author)
    )
    conn.execute(
        "UPDATE translations SET file_hash=? WHERE title=? AND language='en'",
        (file_hash(en_file), title)
    )
    conn.commit()
    conn.close()


def detect_for_pair(text_id: int, translation_id: int):
    """Запускает detect только для конкретного text_id и translation_id."""
    import sqlite3, json, re
    from processing import split_sentences, analyze_sentence
    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    stats = {'found_ru': 0, 'found_en': 0}

    # Оригинал
    row = cursor.execute(
        "SELECT title, language, content FROM texts WHERE text_id=?", (text_id,)
    ).fetchone()
    if row:
        title, lang, content = row
        print(f"\n🔍 Детекция: {title} ({lang})")
        # Пропускаем уже обработанные предложения
        already = cursor.execute(
            "SELECT COUNT(*) FROM sentences WHERE text_id=?", (text_id,)
        ).fetchone()[0]
        if already:
            print(f"   ⏭️  Уже есть {already} предложений, пропускаем")
            stats['found_ru'] = already
        else:
            sentences = split_sentences(content)
            for pos, sentence in enumerate(sentences, 1):
                result = analyze_sentence(sentence, pos, lang)
                if result:
                    cursor.execute("""
                        INSERT INTO sentences
                        (source_type, text_id, translation_id, language, position,
                         sentence, search_word, left_context, right_context, concept_phrase,
                         syntax_tree, pos_tags)
                        VALUES ('original', ?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """, (
                        text_id, lang, pos,
                        result['sentence'], result['search_word'],
                        result['left_context'], result['right_context'], result['concept_phrase'],
                        json.dumps([w['pos'] for w in result['smell_words']])
                    ))
                    stats['found_ru'] += 1
            conn.commit()
            print(f"   ✅ Найдено: {stats['found_ru']}")

    # Перевод
    row = cursor.execute(
        "SELECT title, language, content FROM translations WHERE translation_id=?", (translation_id,)
    ).fetchone()
    if row:
        title, lang, content = row
        print(f"🔍 Детекция: {title} ({lang})")
        already = cursor.execute(
            "SELECT COUNT(*) FROM sentences WHERE translation_id=?", (translation_id,)
        ).fetchone()[0]
        if already:
            print(f"   ⏭️  Уже есть {already} предложений, пропускаем")
            stats['found_en'] = already
        else:
            sentences = split_sentences(content)
            for pos, sentence in enumerate(sentences, 1):
                result = analyze_sentence(sentence, pos, lang)
                if result:
                    cursor.execute("""
                        INSERT INTO sentences
                        (source_type, text_id, translation_id, language, position,
                         sentence, search_word, left_context, right_context, concept_phrase,
                         syntax_tree, pos_tags)
                        VALUES ('translation', NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """, (
                        translation_id, lang, pos,
                        result['sentence'], result['search_word'],
                        result['left_context'], result['right_context'], result['concept_phrase'],
                        json.dumps([w['pos'] for w in result['smell_words']])
                    ))
                    stats['found_en'] += 1
            conn.commit()
            print(f"   ✅ Найдено: {stats['found_en']}")

    conn.close()
    return stats


def auto_align_pair(text_id: int, translation_id: int, threshold: float = 0.65) -> dict:
    from auto_align import auto_align_sentences
    print(f"\n🤖 Автовыравнивание (text_id={text_id}, translation_id={translation_id})...")
    return auto_align_sentences(text_id, translation_id, threshold=threshold)


def print_cosine_distribution(text_id: int, translation_id: int):
    """Выводит распределение cosine_sim для пары."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT cosine_sim FROM alignment a
        JOIN sentences s ON s.sentence_id = a.sentence_ru_id
        WHERE s.text_id = ? AND a.cosine_sim IS NOT NULL
    """, (text_id,)).fetchall()
    conn.close()

    if not rows:
        return

    sims = [r[0] for r in rows]
    buckets = [(0.9, 1.0), (0.8, 0.9), (0.7, 0.8), (0.65, 0.7), (0.0, 0.65)]
    print("\n📈 Распределение cosine_sim:")
    for lo, hi in buckets:
        count = sum(1 for s in sims if lo <= s < hi)
        bar = '█' * count
        print(f"   [{lo:.2f}–{hi:.2f}): {bar} {count}")


# ── Основная функция ─────────────────────────────────────────────────────────

def run_add_book(ru_file: Path, en_file: Path, meta: dict, threshold: float = 0.65):
    """Полный цикл добавления пары книг."""

    print("\n" + "="*60)
    print("📚 ДОБАВЛЕНИЕ КНИГИ")
    print("="*60)
    print(f"   RU: {ru_file}")
    print(f"   EN: {en_file}")

    # Проверка файлов
    for f in (ru_file, en_file):
        if not f.exists():
            print(f"❌ Файл не найден: {f}")
            sys.exit(1)

    # Идемпотентность по hash
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ru_h = file_hash(ru_file)
    en_h = file_hash(en_file)
    ru_exists = hash_exists(cursor, ru_h)
    en_exists = hash_exists(cursor, en_h)
    conn.close()

    if ru_exists and en_exists:
        print("\n⏭️  Оба файла уже загружены (hash совпадает). Пропускаем ingest.")
        text_id, translation_id = get_pair_ids(ru_file, en_file)
    else:
        # 1. Добавить в CSV
        append_to_csv(ru_file, en_file, meta)

        # 2. Ingest
        print("\n📥 Загрузка в БД...")
        load_from_csv()

        # 3. Записать hash
        set_file_hashes(ru_file, en_file)

        # 4. Link
        print("\n🔗 Связывание...")
        link_translations()

        # Получаем ID
        text_id, translation_id = get_pair_ids(ru_file, en_file)
        if not text_id or not translation_id:
            print("❌ Не удалось получить ID пары из БД. Проверьте связывание вручную.")
            sys.exit(1)

        update_csv_status(ru_file.name, 'detected')
        update_csv_status(en_file.name, 'detected')

    # 5. Detect
    detect_stats = detect_for_pair(text_id, translation_id)

    # 6. Auto-align
    align_stats = auto_align_pair(text_id, translation_id, threshold=threshold)

    # Итог
    total_aligned = align_stats.get('inserted', 0)
    print("\n" + "="*60)
    print("✅ ГОТОВО")
    print("="*60)
    print(f"   Ольфакторных RU:   {detect_stats['found_ru']}")
    print(f"   Ольфакторных EN:   {detect_stats['found_en']}")
    print(f"   Выровнено пар:     {total_aligned}")
    print(f"   Ниже порога:       {align_stats.get('below_threshold', 0)}")
    print(f"   Пропущено:         {align_stats.get('skipped', 0)}")

    print_cosine_distribution(text_id, translation_id)

    if total_aligned > 0:
        update_csv_status(ru_file.name, 'aligned')
        update_csv_status(en_file.name, 'aligned')


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Добавить пару книг в корпус")
    parser.add_argument('--ru', required=True, help='Путь к русскому файлу')
    parser.add_argument('--en', required=True, help='Путь к английскому файлу')
    parser.add_argument('--meta', nargs='*', default=[],
                        help='Метаданные: author="..." title="..." year=1869 genre=prose translator="..."')
    parser.add_argument('--threshold', type=float, default=0.65,
                        help='Порог cosine_sim для автовыравнивания (default: 0.65)')
    args = parser.parse_args()

    ru_file = Path(args.ru)
    en_file = Path(args.en)

    # Разбираем --meta key=val
    meta = {}
    for item in args.meta:
        if '=' in item:
            k, v = item.split('=', 1)
            meta[k.strip()] = v.strip()

    # Если пути относительные — ищем в DATA_DIR
    if not ru_file.is_absolute() and not ru_file.exists():
        ru_file = DATA_DIR / ru_file
    if not en_file.is_absolute() and not en_file.exists():
        en_file = DATA_DIR / en_file

    run_add_book(ru_file, en_file, meta, threshold=args.threshold)


if __name__ == '__main__':
    main()
