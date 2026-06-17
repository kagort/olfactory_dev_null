# src/parse_sentences.py
"""
Грамматический разбор предложений через Stanza (RU) и spaCy (EN).

Запуск:
    python src/parse_sentences.py                  — разбор RU и EN
    python src/parse_sentences.py --lang ru        — только RU
    python src/parse_sentences.py --lang en        — только EN
    python src/parse_sentences.py --ru 1           — только предложения text_id=1
    python src/parse_sentences.py --en 1           — только предложения translation_id=1
    python src/parse_sentences.py --limit 100      — не более 100 предложений
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DB_PATH
import grammar


COMMIT_EVERY = 50


def parse_sentences(lang: str, ru_id: int = None, en_id: int = None, limit: int = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    conditions = ["(gram_structure IS NULL OR gram_structure = '')"]
    params = []

    if lang == 'ru':
        conditions.append("language = 'ru'")
        conditions.append("source_type = 'original'")
        if ru_id is not None:
            conditions.append("text_id = ?")
            params.append(ru_id)
    elif lang == 'en':
        conditions.append("language = 'en'")
        conditions.append("source_type = 'translation'")
        if en_id is not None:
            conditions.append("translation_id = ?")
            params.append(en_id)

    where = " AND ".join(conditions)
    query = f"SELECT sentence_id, sentence, language FROM sentences WHERE {where} ORDER BY sentence_id"
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query, params)
    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        print(f"Нет предложений для разбора (lang={lang})")
        conn.close()
        return

    print(f"Разбор {total} предложений (lang={lang})...")

    for i, (sentence_id, sentence, language) in enumerate(rows, 1):
        print(f"\r{i}/{total}", end="", flush=True)

        try:
            if language == 'ru':
                gram = grammar.parse_ru(sentence)
                gram_json = json.dumps(grammar.to_gram_json(gram), ensure_ascii=False)
                cur.execute(
                    "UPDATE sentences SET gram_structure = ?, gram_json = ? WHERE sentence_id = ?",
                    (gram, gram_json, sentence_id)
                )
            else:
                gram = grammar.parse_en(sentence)
                cur.execute(
                    "UPDATE sentences SET gram_structure = ? WHERE sentence_id = ?",
                    (gram, sentence_id)
                )
        except Exception as e:
            print(f"\n  Ошибка sentence_id={sentence_id}: {e}")

        if i % COMMIT_EVERY == 0:
            conn.commit()

    conn.commit()
    print(f"\nГотово: обработано {total} предложений.")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Грамматический разбор предложений')
    parser.add_argument('--ru',   type=int, default=None, help='text_id для RU предложений')
    parser.add_argument('--en',   type=int, default=None, help='translation_id для EN предложений')
    parser.add_argument('--lang', type=str, default='both', choices=['ru', 'en', 'both'],
                        help='Язык для разбора (по умолчанию: both)')
    parser.add_argument('--limit', type=int, default=None, help='Максимум предложений')
    args = parser.parse_args()

    langs = ['ru', 'en'] if args.lang == 'both' else [args.lang]

    for lang in langs:
        parse_sentences(
            lang=lang,
            ru_id=args.ru if lang == 'ru' else None,
            en_id=args.en if lang == 'en' else None,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
