# src/manual_review_v2.py
"""
Интерактивная ручная разметка непривязанных EN-предложений.
Пользователь вводит ключевые слова, система ищет по полному сырому RU тексту.

Запуск:
    python run.py review --ru 1 --en 1
    python run.py review --ru 1 --en 1 --parse
"""

import re
import sqlite3
import argparse
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import syntok.segmenter as segmenter

from config import DB_PATH

# ── Переводчик EN→RU ──────────────────────────────────────────────────────────

_translator = None
_tok = None
_OPUS_MT_PATH = r"C:\models\opus-mt-en-ru"


def _get_translator():
    global _translator, _tok
    if _translator is None:
        from transformers import MarianMTModel, MarianTokenizer
        import os
        print("🔄 Загружаю переводчик...")
        _tok = MarianTokenizer(
            source_spm=os.path.join(_OPUS_MT_PATH, "source.spm"),
            target_spm=os.path.join(_OPUS_MT_PATH, "target.spm"),
            vocab=os.path.join(_OPUS_MT_PATH, "vocab.json"),
            source_lang="en",
            target_lang="ru",
        )
        _translator = MarianMTModel.from_pretrained(_OPUS_MT_PATH)
        print("✅ Переводчик загружен")
    return _translator, _tok


def translate_batch(texts: List[str]) -> List[str]:
    model, tok = _get_translator()
    results = []
    for i, text in enumerate(texts, 1):
        inputs = tok([text], return_tensors="pt", padding=True, truncation=True, max_length=512)
        tokens = model.generate(**inputs)
        results.append(tok.decode(tokens[0], skip_special_tokens=True))
        print(f"  Перевод: {i}/{len(texts)}", end="\r", flush=True)
    print()
    return results


# ── Лемматизатор ─────────────────────────────────────────────────────────────

_morph = None


def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def lemmatize(word: str) -> str:
    morph = _get_morph()
    return morph.parse(word.lower())[0].normal_form


# ── Пополнение словаря ────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "config.py"
_added_words: List[str] = []


def add_olfactory_word(word: str, lang: str = 'ru') -> None:
    lem = lemmatize(word) if lang == 'ru' else word.lower()
    text = _CONFIG_PATH.read_text(encoding='utf-8')
    pattern = rf"('{lang}':\s*{{[^}}]*)}}"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        print(f"  ❌ Не найден блок '{lang}' в config.py")
        return
    block = match.group(0)
    if f"'{lem}'" in block or f'"{lem}"' in block:
        print(f"  ℹ️  «{lem}» уже есть в словаре.")
        return
    new_block = block.rstrip('}').rstrip() + f"\n        '{lem}',\n    }}"
    new_text = text[:match.start()] + new_block + text[match.end():]
    _CONFIG_PATH.write_text(new_text, encoding='utf-8')
    _added_words.append(lem)
    print(f"  ✅ «{lem}» добавлено в OLFACTORY_WORDS['{lang}']")


# ── Разбивка текста ───────────────────────────────────────────────────────────

def split_raw_text(text: str) -> List[Dict]:
    sentences = []
    pos = 0
    for paragraph in segmenter.process(text):
        for sentence in paragraph:
            s = " ".join(t.value for t in sentence).strip()
            if s:
                sentences.append({"position": pos, "sentence": s})
                pos += 1
    return sentences


# ── Построение индексов ───────────────────────────────────────────────────────

def build_indexes(raw_sentences: List[Dict]):
    """Возвращает lemma_index и form_index: {ключ: [position, ...]}"""
    lemma_index: Dict[str, List[int]] = defaultdict(list)
    form_index:  Dict[str, List[int]] = defaultdict(list)

    for item in raw_sentences:
        pos = item["position"]
        for word in item["sentence"].split():
            w = word.strip(".,!?;:—–()«»\"'").lower()
            if not w or len(w) < 2:
                continue
            form_index[w].append(pos)
            lem = lemmatize(w)
            lemma_index[lem].append(pos)

    # убираем дубли позиций
    for d in (lemma_index, form_index):
        for k in d:
            d[k] = sorted(set(d[k]))

    return lemma_index, form_index


# ── Поиск кандидатов ──────────────────────────────────────────────────────────

def search_candidates(
    words: List[str],
    lemma_index: Dict[str, List[int]],
    form_index:  Dict[str, List[int]],
) -> List[Tuple[int, List[str]]]:
    """Возвращает [(position, [matched_words]), ...] по убыванию совпадений.
    Если слов больше одного — возвращает только предложения где совпало ≥2 слов."""
    pos_matches: Dict[int, List[str]] = defaultdict(list)

    for w in words:
        wl = w.lower()
        lem = lemmatize(wl)
        positions = set(lemma_index.get(lem, [])) | set(form_index.get(wl, []))
        for p in positions:
            pos_matches[p].append(w)

    min_matches = 2 if len(words) > 1 else 1
    results = [
        (pos, matched) for pos, matched in pos_matches.items()
        if len(matched) >= min_matches
    ]
    results.sort(key=lambda x: (-len(x[1]), x[0]))
    return results


# ── Вывод кандидата с контекстом ─────────────────────────────────────────────

def print_candidate_with_context(
    position: int,
    matched_words: List[str],
    pos_to_sentence: Dict[int, str],
    all_positions: List[int],
):
    idx = all_positions.index(position) if position in all_positions else -1
    context_positions = all_positions[max(0, idx - 2): idx + 3] if idx >= 0 else [position]

    print(f"  ─────────────────────────────────────────")
    print(f"  pos={position}  [совпало: {', '.join(matched_words)}]")
    for p in context_positions:
        s = pos_to_sentence.get(p, "")
        if p != position:
            s = s[:120]
        prefix = "  >>>" if p == position else "     "
        print(f"  {prefix} {s}")
    print()


# ── Сохранение пары ──────────────────────────────────────────────────────────

def save_pair(
    cursor,
    ru_text_id: int,
    en_sentence_id: int,
    position: int,
    sentence: str,
    do_parse: bool,
    stats: Dict,
):
    # Найти или создать sentence_id
    row = cursor.execute(
        "SELECT sentence_id FROM sentences WHERE text_id=? AND sentence=? AND source_type='original'",
        (ru_text_id, sentence)
    ).fetchone()

    if row:
        ru_id = row[0]
    else:
        gram_structure, gram_json = None, None
        if do_parse:
            try:
                from grammar import parse_ru
                result = parse_ru(sentence)
                if result:
                    gram_structure = result.get("structure")
                    import json
                    gram_json = json.dumps(result, ensure_ascii=False)
            except Exception:
                pass

        cursor.execute(
            """INSERT INTO sentences
               (source_type, text_id, position, sentence, language,
                search_word, gram_structure, gram_json)
               VALUES ('original', ?, ?, ?, 'ru', NULL, ?, ?)""",
            (ru_text_id, position, sentence, gram_structure, gram_json)
        )
        ru_id = cursor.lastrowid

    # Проверить дубль
    existing = cursor.execute(
        "SELECT alignment_id FROM alignment WHERE sentence_ru_id=? AND sentence_en_id=?",
        (ru_id, en_sentence_id)
    ).fetchone()

    if existing:
        print("  ℹ️  Эта пара уже есть в БД.\n")
        return

    cursor.execute(
        """INSERT INTO alignment
           (sentence_ru_id, sentence_en_id, cosine_sim, auto_aligned, assisted)
           VALUES (?, ?, NULL, 0, 1)""",
        (ru_id, en_sentence_id)
    )
    cursor.connection.commit()
    stats["confirmed"] += 1
    print(f"  ✅ Сохранено (ru_id={ru_id}, pos={position})\n")


# ── Основная функция ──────────────────────────────────────────────────────────

def review_unmatched(ru_text_id: int, translation_id: int, do_parse: bool = False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Добавить колонку assisted если нет
    try:
        cursor.execute("ALTER TABLE alignment ADD COLUMN assisted INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    # Непривязанные EN предложения
    en_rows = cursor.execute("""
        SELECT s.sentence_id, s.position, s.sentence
        FROM sentences s
        WHERE s.translation_id = ? AND s.source_type = 'translation'
          AND s.sentence_id NOT IN (
              SELECT sentence_en_id FROM alignment
          )
        ORDER BY s.position
    """, (translation_id,)).fetchall()

    if not en_rows:
        print("✅ Все EN-предложения уже привязаны.")
        conn.close()
        return

    print(f"\n📊 Непривязанных EN: {len(en_rows)}")

    # Сырой RU текст из БД
    content_row = cursor.execute(
        "SELECT content FROM texts WHERE text_id=?", (ru_text_id,)
    ).fetchone()

    if not content_row or not content_row[0]:
        print(f"❌ Не найден content для text_id={ru_text_id}")
        conn.close()
        return

    print("📖 Разбиваю RU текст на предложения...")
    raw_sentences = split_raw_text(content_row[0])
    pos_to_sentence = {item["position"]: item["sentence"] for item in raw_sentences}
    all_positions = [item["position"] for item in raw_sentences]
    print(f"   Предложений в сыром тексте: {len(raw_sentences)}")

    print("\n🔍 Строю индексы лемм...")
    lemma_index, form_index = build_indexes(raw_sentences)

    print("\n🔄 Перевожу EN→RU...")
    en_texts = [r[2] for r in en_rows]
    translations = translate_batch(en_texts)

    stats = {"confirmed": 0, "skipped": 0}

    print(f"\n{'═'*68}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(en_rows)} предложений")
    print(f"   Управление: число=выбрать по pos | r=новый поиск | a=добавить слово в словарь | s=пропустить | q=выйти")
    print(f"{'═'*68}\n")

    for idx, (en_id, en_pos, en_text) in enumerate(en_rows):
        translation = translations[idx]

        print(f"{'═'*68}")
        print(f"[{idx+1}/{len(en_rows)}] EN (pos={en_pos}):")
        print(f"  \"{en_text}\"")
        print(f"  → RU: \"{translation}\"")
        print()

        skipped = False
        saved = False
        while not skipped and not saved:
            query = input("  Введите слова для поиска (a=добавить в словарь / Enter=пропустить / q=выйти): ").strip()

            if query.lower() == 'q':
                print(f"\n✅ Прервано. Привязано: {stats['confirmed']}, пропущено: {stats['skipped']}, осталось: {len(en_rows)-idx-1}")
                conn.close()
                return

            if query.lower() == 'a':
                word_to_add = input("  Слово для добавления в словарь: ").strip()
                lang_choice = input("  Язык (ru/en, Enter=ru): ").strip().lower() or 'ru'
                if word_to_add and lang_choice in ('ru', 'en'):
                    add_olfactory_word(word_to_add, lang=lang_choice)
                continue

            if query == '':
                stats["skipped"] += 1
                skipped = True
                break

            words = query.split()
            candidates = search_candidates(words, lemma_index, form_index)

            if not candidates:
                print("  ❌ Ничего не найдено. Попробуйте другие слова.\n")
                continue

            if len(candidates) > 20:
                print(f"  ⚠️  Найдено {len(candidates)} совпадений — слишком много. Уточните запрос.\n")
                for p, mw in candidates[:5]:
                    print(f"    pos={p}: {pos_to_sentence.get(p,'')[:80]}")
                print(f"    ... и ещё {len(candidates)-5}")
                print()
                continue

            print()
            for p, mw in candidates:
                print_candidate_with_context(p, mw, pos_to_sentence, all_positions)

            while True:
                choice = input("  Введите pos (несколько через пробел / r=новый поиск / s=пропустить / q=выйти): ").strip().lower()

                if choice == 'q':
                    print(f"\n✅ Прервано. Привязано: {stats['confirmed']}, пропущено: {stats['skipped']}, осталось: {len(en_rows)-idx-1}")
                    conn.close()
                    return

                if choice == 's':
                    stats["skipped"] += 1
                    skipped = True
                    break

                if choice == 'r':
                    print(f"\n  EN: \"{en_text}\"")
                    print(f"  → RU: \"{translation}\"\n")
                    break

                parts = choice.split()
                if all(p.isdigit() for p in parts) and parts:
                    valid = True
                    for p_str in parts:
                        pos = int(p_str)
                        if pos not in pos_to_sentence:
                            print(f"  ❌ Позиция {pos} не найдена в тексте.")
                            valid = False
                            break
                    if not valid:
                        continue
                    for p_str in parts:
                        pos = int(p_str)
                        sentence = pos_to_sentence[pos]
                        save_pair(cursor, ru_text_id, en_id, pos, sentence, do_parse, stats)
                    saved = True
                    break
                else:
                    print("  ❌ Неверный ввод.")

    conn.close()
    print(f"\n{'═'*68}")
    print(f"✅ Сессия завершена.")
    print(f"   Привязано:  {stats['confirmed']}")
    print(f"   Пропущено:  {stats['skipped']}")
    print(f"   Осталось:   {len(en_rows) - stats['confirmed'] - stats['skipped']}")
    if _added_words:
        print(f"\n📖 Добавлено в словарь: {', '.join(_added_words)}")
        print(f"   Запустите 'python run.py detect --clear' и 'python run.py auto-align' для обновления.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ru',    type=int, required=True)
    parser.add_argument('--en',    type=int, required=True)
    parser.add_argument('--parse', action='store_true')
    args = parser.parse_args()

    review_unmatched(
        ru_text_id=args.ru,
        translation_id=args.en,
        do_parse=args.parse,
    )


if __name__ == '__main__':
    main()
