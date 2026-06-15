# src/manual_review_v2.py
"""
Интерактивная ручная разметка непривязанных EN-предложений v2.
Поиск совпадений ведётся по СЫРОМУ RU тексту (не только по ольфакторным).

Алгоритм:
  1. Непривязанные EN-предложения + якорные пары из alignment.
  2. Сырой RU текст читается из data/books/raw/<filename> (разбивается syntok).
  3. EN→RU перевод через Helsinki-NLP opus-mt-en-ru.
  4. Гибридный скор = Жаккар(леммы) + косинус(LaBSE) + позиционный_скор.
  5. Интерактивный UI с контекстом (2 предложения до/после).

Запуск:
    python run.py review --ru 1 --en 1
    python run.py review --ru 1 --en 1 --top 5 --parse
"""

import re
import sys
import sqlite3
import argparse
import numpy as np
from pathlib import Path
from statistics import median
from typing import List, Dict, Tuple, Optional

import syntok.segmenter as segmenter

from config import DB_PATH, DATA_DIR
from auto_align import get_model, _cosine_matrix

# ── Переводчик EN→RU ──────────────────────────────────────────────────────────

_translator = None
_tok = None
_OPUS_MT_PATH = r"C:\models\opus-mt-en-ru"


def _get_translator():
    global _translator, _tok
    if _translator is None:
        from transformers import MarianMTModel, MarianTokenizer
        import os
        print("Загружаю переводчик из локальной папки...")
        _tok = MarianTokenizer(
            source_spm=os.path.join(_OPUS_MT_PATH, "source.spm"),
            target_spm=os.path.join(_OPUS_MT_PATH, "target.spm"),
            vocab=os.path.join(_OPUS_MT_PATH, "vocab.json"),
            source_lang="en",
            target_lang="ru",
        )
        _translator = MarianMTModel.from_pretrained(_OPUS_MT_PATH)
        print("Переводчик загружен")
    return _translator, _tok


def translate_en_ru(text: str) -> str:
    model, tok = _get_translator()
    inputs = tok([text], return_tensors="pt", padding=True, truncation=True, max_length=512)
    tokens = model.generate(**inputs)
    return tok.decode(tokens[0], skip_special_tokens=True)


# ── Стоп-слова (расширенный список ~100 слов) ─────────────────────────────────

_STOP_RU = {
    'и', 'в', 'не', 'на', 'с', 'что', 'а', 'это', 'из', 'по', 'к', 'но',
    'он', 'она', 'они', 'мы', 'вы', 'я', 'его', 'её', 'их', 'как', 'или',
    'то', 'уже', 'всё', 'так', 'же', 'был', 'была', 'были', 'есть', 'за',
    'со', 'ещё', 'тут', 'там', 'при', 'об', 'от', 'до', 'без', 'под', 'над',
    'для', 'между', 'через', 'после', 'перед', 'во', 'будет', 'бы', 'ли',
    'же', 'вот', 'если', 'чтобы', 'когда', 'где', 'куда', 'откуда', 'потому',
    'поэтому', 'однако', 'хотя', 'пока', 'чем', 'тем', 'всего', 'только',
    'уже', 'даже', 'очень', 'более', 'менее', 'самый', 'весь', 'каждый',
    'другой', 'такой', 'этот', 'который', 'свой', 'наш', 'ваш', 'мой', 'твой',
    'ни', 'нет', 'да', 'нас', 'вас', 'им', 'ему', 'ей', 'мне', 'тебе',
    'себе', 'один', 'два', 'три', 'четыре', 'пять',
}

# ── Лемматизация ──────────────────────────────────────────────────────────────

_morph = None


def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def lemmatize_word(word: str) -> str:
    return _get_morph().parse(word)[0].normal_form


def lemmatize_text(text: str) -> List[str]:
    """Возвращает список лемм без стоп-слов."""
    morph = _get_morph()
    lemmas = []
    for raw in re.findall(r'[а-яёА-ЯЁ]+', text.lower()):
        lemma = morph.parse(raw)[0].normal_form
        if lemma not in _STOP_RU:
            lemmas.append(lemma)
    return lemmas


# ── Разбивка сырого текста через syntok ──────────────────────────────────────

def split_raw_text(text: str) -> List[Dict]:
    """
    Разбивает текст syntok-ом.
    Возвращает список {'position': int, 'sentence': str}, нумерация с 0.
    """
    result = []
    pos = 0
    for paragraph in segmenter.process(text):
        for sentence in paragraph:
            sent_text = ' '.join([token.value for token in sentence])
            sent_text = re.sub(r'\s+', ' ', sent_text).strip()
            if sent_text:
                result.append({'position': pos, 'sentence': sent_text})
                pos += 1
    return result


# ── Жаккар ───────────────────────────────────────────────────────────────────

def jaccard(lemmas_a: List[str], lemmas_b: List[str]) -> float:
    set_a = set(lemmas_a)
    set_b = set(lemmas_b)
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ── Позиционный скор ─────────────────────────────────────────────────────────

def compute_position_score(
    pos_en: int,
    pos_ru_candidate: int,
    anchor_pairs: List[Tuple[int, int]],
    total_ru: int,
) -> float:
    """Возвращает position_score в [0, 1] для кандидата."""
    n = len(anchor_pairs)
    if n == 0:
        return 0.0

    offsets = [ru - en for (en, ru) in anchor_pairs]
    offset = median(offsets)
    expected = pos_en + offset

    window_frac = 0.30 if n < 5 else 0.20
    window = window_frac * total_ru

    distance = abs(pos_ru_candidate - expected)
    if window <= 0:
        return 0.0
    if distance <= window:
        return 1.0 - (distance / window)
    return 0.0


def compute_hybrid_weights(n_anchors: int) -> Tuple[float, float, float]:
    """Возвращает (w_lex, w_cos, w_pos)."""
    if n_anchors == 0:
        return 0.5, 0.5, 0.0
    elif n_anchors < 5:
        return 0.45, 0.45, 0.10
    else:
        return 0.40, 0.40, 0.20


# ── Сохранение пары ──────────────────────────────────────────────────────────

def _ensure_assisted_column(cursor):
    try:
        cursor.execute("ALTER TABLE alignment ADD COLUMN assisted INTEGER DEFAULT 0")
    except Exception:
        pass  # уже существует


def _save_pair(
    conn,
    cursor,
    ru_sentence_text: str,
    ru_text_id: int,
    en_sentence_id: int,
    cosine_sim: float,
    stats: dict,
    do_parse: bool = False,
) -> Optional[int]:
    """
    Ищет RU предложение по тексту. Если не найдено — вставляет.
    Затем пишет в alignment. Возвращает sentence_id RU-предложения или None при ошибке.
    """
    # 1. Поиск по тексту и text_id
    row = cursor.execute(
        "SELECT sentence_id FROM sentences WHERE sentence=? AND text_id=?",
        (ru_sentence_text, ru_text_id)
    ).fetchone()

    if row:
        ru_id = row[0]
    else:
        # 2. INSERT нового предложения
        gram_structure = None
        gram_json = None
        if do_parse:
            try:
                from grammar import parse_ru, parse_to_json
                gram_structure = parse_ru(ru_sentence_text)
                gram_json = parse_to_json(gram_structure)
            except Exception as e:
                print(f"  Предупреждение: парсинг не удался: {e}")

        cursor.execute("""
            INSERT INTO sentences
            (source_type, text_id, translation_id, language, position,
             sentence, search_word, gram_structure, gram_json)
            VALUES ('original', ?, NULL, 'ru', NULL, ?, NULL, ?, ?)
        """, (ru_text_id, ru_sentence_text, gram_structure, gram_json))
        ru_id = cursor.lastrowid
        print(f"  [NEW] Добавлено новое предложение sentence_id={ru_id}")

    # 3. Проверка дублей
    existing = cursor.execute(
        "SELECT alignment_id FROM alignment WHERE sentence_ru_id=? AND sentence_en_id=?",
        (ru_id, en_sentence_id)
    ).fetchone()
    if existing:
        print("  Эта пара уже есть в БД.\n")
        return ru_id

    # 4. INSERT в alignment
    cursor.execute("""
        INSERT INTO alignment (sentence_ru_id, sentence_en_id, cosine_sim, auto_aligned, assisted)
        VALUES (?, ?, ?, 0, 1)
    """, (ru_id, en_sentence_id, round(cosine_sim, 4)))
    stats['confirmed'] += 1
    conn.commit()
    print(f"  Сохранено (sim={cosine_sim:.3f})\n")
    return ru_id


# ── Контекстное окно ──────────────────────────────────────────────────────────

def _context_lines(raw_sentences: List[Dict], pos: int, window: int = 2) -> List[str]:
    """Возвращает строки контекста для отображения."""
    lines = []
    n = len(raw_sentences)
    for i in range(max(0, pos - window), min(n, pos + window + 1)):
        sent = raw_sentences[i]['sentence']
        prefix = ">>>" if i == pos else "   "
        lines.append(f"  {prefix} {sent[:120]}")
    return lines


# ── Основная функция ──────────────────────────────────────────────────────────

def review_unmatched_v2(
    ru_text_id: int,
    translation_id: int,
    top_k: int = 3,
    do_parse: bool = False,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    _ensure_assisted_column(cursor)
    conn.commit()

    # ── 1. Загрузка данных ────────────────────────────────────────────────────

    # Непривязанные EN-предложения
    df_en_rows = cursor.execute("""
        SELECT s.sentence_id, s.position, s.sentence
        FROM sentences s
        WHERE s.translation_id = ?
          AND s.language = 'en'
          AND s.sentence_id NOT IN (
              SELECT sentence_en_id FROM alignment WHERE sentence_en_id IS NOT NULL
          )
        ORDER BY s.position
    """, (translation_id,)).fetchall()

    if not df_en_rows:
        print("Все EN-предложения уже привязаны.")
        conn.close()
        return

    # Якорные пары: (pos_en, pos_ru)
    anchor_rows = cursor.execute("""
        SELECT s_en.position, s_ru.position
        FROM alignment a
        JOIN sentences s_ru ON s_ru.sentence_id = a.sentence_ru_id
        JOIN sentences s_en ON s_en.sentence_id = a.sentence_en_id
        WHERE s_ru.text_id = ?
    """, (ru_text_id,)).fetchall()
    anchor_pairs: List[Tuple[int, int]] = [(r[0], r[1]) for r in anchor_rows]

    # Сырой текст из поля content
    content_row = cursor.execute(
        "SELECT content FROM texts WHERE text_id=?", (ru_text_id,)
    ).fetchone()
    if not content_row or not content_row[0]:
        print(f"Ошибка: не найден content для text_id={ru_text_id}")
        conn.close()
        return

    print(f"Читаю сырой текст из БД (text_id={ru_text_id})...")
    raw_text = content_row[0]
    raw_sentences = split_raw_text(raw_text)
    total_ru = len(raw_sentences)

    # ── 2. Pre-computation ────────────────────────────────────────────────────

    en_sentences = [r[2] for r in df_en_rows]
    total_en = len(en_sentences)

    # Перевод EN→RU
    print(f"\nПеревожу {total_en} EN-предложений...")
    _get_translator()
    translations = []
    for i, s in enumerate(en_sentences, 1):
        translations.append(translate_en_ru(s))
        print(f"  {i}/{total_en}", end="\r", flush=True)
    print()

    # Леммы переводов
    print("Лемматизирую переводы...")
    tr_lemmas = [lemmatize_text(t) for t in translations]

    # Леммы сырых RU предложений (кэш)
    print("Лемматизирую сырой RU текст...")
    ru_lemmas_cache = [lemmatize_text(s['sentence']) for s in raw_sentences]

    # Векторы (LaBSE)
    labse = get_model()
    print("Кодирую сырые RU предложения через LaBSE...")
    raw_ru_texts = [s['sentence'] for s in raw_sentences]
    ru_vecs = labse.encode(raw_ru_texts, show_progress_bar=True, convert_to_numpy=True)

    print("Кодирую переводы через LaBSE...")
    tr_vecs = labse.encode(translations, show_progress_bar=True, convert_to_numpy=True)

    # Матрица косинусного сходства (n_raw_ru × n_en)
    # cos_matrix[i, j] = сходство ru[i] с translation[j]
    cos_matrix = _cosine_matrix(ru_vecs, tr_vecs)  # shape: (total_ru, total_en)

    # ── 3-4. Гибридный скоринг + позиция ─────────────────────────────────────

    stats = {'confirmed': 0, 'skipped': 0}

    print(f"\n{'='*48}")
    print(f"РУЧНАЯ РАЗМЕТКА — {total_en} предложений")
    print(f"Управление: 1-{top_k}=выбрать  f=поиск по слову  s=пропустить  q=выйти")
    print(f"{'='*48}\n")

    for j_idx, en_row in enumerate(df_en_rows):
        en_sid, en_pos, en_text = en_row
        translated = translations[j_idx]
        tr_lem = tr_lemmas[j_idx]

        w_lex, w_cos, w_pos = compute_hybrid_weights(len(anchor_pairs))

        # Скоры для каждого RU-предложения
        scores = []
        for i, raw_sent in enumerate(raw_sentences):
            lex = jaccard(tr_lem, ru_lemmas_cache[i])
            cos = float(cos_matrix[i, j_idx])
            if w_pos > 0:
                pos_s = compute_position_score(en_pos, raw_sent['position'], anchor_pairs, total_ru)
            else:
                pos_s = 0.0
            score = w_lex * lex + w_cos * cos + w_pos * pos_s
            scores.append((score, lex, cos, pos_s, i))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scores[:top_k]

        # Отображение
        print(f"{'='*48}")
        offset_str = ""
        if anchor_pairs:
            offsets = [ru - en for (en, ru) in anchor_pairs]
            off_val = median(offsets)
            mode = "калиброванный" if len(anchor_pairs) >= 5 else "частичный"
            offset_str = f"Якорей: {len(anchor_pairs)} | Смещение: {off_val:+.0f} | Режим: {mode}"
        else:
            offset_str = "Якорей: 0 | Режим: без позиции"

        print(f"[{j_idx+1}/{total_en}] EN (pos={en_pos}):")
        print(f'  "{en_text[:120]}"')
        print(f'  -> RU: "{translated[:120]}"')
        print(f"  {offset_str}")
        print()

        candidates = []
        for rank, (score, lex, cos, pos_s, ru_i) in enumerate(top_candidates, 1):
            raw_sent = raw_sentences[ru_i]
            pos_mark = "OK" if pos_s > 0 else "?"
            print(f"  [{rank}] score={score:.2f}  (lex={lex:.2f}  sim={cos:.2f}  pos={pos_mark})  pos={raw_sent['position']}")
            ctx = _context_lines(raw_sentences, ru_i)
            for line in ctx:
                print(line)
            print()
            candidates.append((raw_sent, cos, ru_i))

        print(f"  Управление: 1-{top_k}=выбрать  f=поиск по слову  s=пропустить  q=выйти")
        print(f"{'='*48}")

        while True:
            choice = input("  Выбор: ").strip().lower()

            if choice == 'q':
                conn.close()
                print(f"\nПрервано. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")
                return

            if choice == 's':
                stats['skipped'] += 1
                break

            if choice == 'f':
                kw = input("  Слово для поиска: ").strip()
                if not kw:
                    continue
                kw_lemma = lemmatize_word(kw.lower())
                matches = [
                    s for s in raw_sentences
                    if kw_lemma in ru_lemmas_cache[s['position']]
                ]
                if not matches:
                    print(f"  Ничего не найдено по лемме «{kw_lemma}»")
                else:
                    print(f"  Найдено {len(matches)} предложений:")
                    for m in matches:
                        print(f"    pos={m['position']}  \"{m['sentence'][:100]}\"")
                pos_input = input("  Введите position для сохранения (или Enter чтобы продолжить): ").strip()
                if pos_input.isdigit():
                    pos_num = int(pos_input)
                    matching = [s for s in raw_sentences if s['position'] == pos_num]
                    if not matching:
                        print(f"  Позиция {pos_num} не найдена.")
                    else:
                        chosen = matching[0]
                        # Косинусное сходство с этим предложением
                        sim = float(cos_matrix[pos_num, j_idx]) if pos_num < total_ru else 0.0
                        ru_id = _save_pair(
                            conn, cursor,
                            chosen['sentence'], ru_text_id,
                            en_sid, sim, stats, do_parse
                        )
                        if ru_id is not None and stats.get('confirmed', 0) > 0:
                            # Обновляем якоря
                            anchor_pairs.append((en_pos, chosen['position']))
                        break
                continue

            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                idx = int(choice) - 1
                raw_sent, cos_sim, ru_i = candidates[idx]
                ru_id = _save_pair(
                    conn, cursor,
                    raw_sent['sentence'], ru_text_id,
                    en_sid, cos_sim, stats, do_parse
                )
                if ru_id is not None:
                    anchor_pairs.append((en_pos, raw_sent['position']))
                break

            print("  Неверный ввод.")

    conn.close()
    print(f"\nГОТОВО. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ручная разметка v2 (по сырому тексту)")
    parser.add_argument('--ru',    type=int, required=True,  help="text_id русского оригинала")
    parser.add_argument('--en',    type=int, required=True,  help="translation_id EN перевода")
    parser.add_argument('--top',   type=int, default=3,      help="Количество кандидатов (по умолч. 3)")
    parser.add_argument('--parse', action='store_true',      help="Разбирать грамматику новых предложений")
    args = parser.parse_args()

    review_unmatched_v2(
        ru_text_id=args.ru,
        translation_id=args.en,
        top_k=args.top,
        do_parse=args.parse,
    )


if __name__ == '__main__':
    main()
