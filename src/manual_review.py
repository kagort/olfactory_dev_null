# src/manual_review.py
"""
Интерактивная проверка непривязанных EN-предложений.

Алгоритм поиска кандидатов (гибридный):
  1. Позиционное окно: offset = median(en_pos - ru_pos) по выровненным парам,
     поиск только в диапазоне [en_pos - offset ± tolerance].
  2. Перевод EN→RU (Helsinki-NLP/opus-mt-en-ru).
  3. Гибридный скор = 0.5 × cosine_sim + 0.5 × word_overlap(перевод, RU).
  4. Показывает топ-K кандидатов. Пользователь подтверждает или пропускает.

Запуск:
    python src/manual_review.py --ru 1 --en 1
    python src/manual_review.py --ru 1 --en 1 --top 5 --tolerance 300
    python src/manual_review.py --ru 1 --en 1 --no-window
"""

import sqlite3
import argparse
import numpy as np
import pandas as pd

from config import DB_PATH
from auto_align import get_model, _cosine_matrix

# ── Лексический скоринг без перевода ─────────────────────────────────────────
# Простая транслитерация EN→RU для имён собственных и ключевых слов

_TRANSLIT = str.maketrans(
    'abcdefghijklmnopqrstuvwxyz',
    'абцдефгхийклмнопqрстуввхыз'
)

_TRANSLIT_MAP = {
    'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е', 'f': 'ф',
    'g': 'г', 'h': 'х', 'i': 'и', 'j': 'й', 'k': 'к', 'l': 'л',
    'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р',
    's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс',
    'y': 'й', 'z': 'з',
    'ch': 'ч', 'sh': 'ш', 'th': 'з', 'ph': 'ф', 'zh': 'ж',
}

_STOP_EN = {'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'of',
            'is', 'was', 'were', 'it', 'he', 'she', 'they', 'we', 'i',
            'that', 'this', 'with', 'from', 'by', 'for', 'as', 'but'}
_STOP_RU = {'и', 'в', 'не', 'на', 'с', 'что', 'а', 'это', 'из', 'по', 'к',
            'но', 'он', 'она', 'они', 'мы', 'вы', 'я', 'его', 'её', 'их',
            'как', 'или', 'то', 'уже', 'всё', 'так', 'же', 'был', 'была',
            'были', 'есть', 'за', 'со', 'ещё', 'тут', 'там'}


def _transliterate(word: str) -> str:
    """Простая транслитерация английского слова в кириллицу."""
    word = word.lower()
    result = ''
    i = 0
    while i < len(word):
        pair = word[i:i+2]
        if pair in _TRANSLIT_MAP:
            result += _TRANSLIT_MAP[pair]
            i += 2
        elif word[i] in _TRANSLIT_MAP:
            result += _TRANSLIT_MAP[word[i]]
            i += 1
        else:
            i += 1
    return result


def _key_words_en(text: str):
    """Извлекает ключевые слова EN: имена собственные + существительные длиннее 4 букв."""
    words = text.split()
    result = set()
    for i, w in enumerate(words):
        clean = w.strip('.,!?;:—–()«»"\'').lower()
        if clean in _STOP_EN or len(clean) < 3:
            continue
        # Имя собственное — заглавная буква не в начале предложения
        if i > 0 and w[0].isupper():
            result.add(_transliterate(clean))
        # Длинные содержательные слова
        elif len(clean) > 4:
            result.add(_transliterate(clean))
    return result


def word_overlap(en_text: str, ru_sentence: str) -> float:
    """
    Скор совпадения: транслитерированные EN-слова vs токены RU-предложения.
    Дополнительно: прямой поиск EN-слов в RU (цифры, аббревиатуры).
    """
    en_keys = _key_words_en(en_text)
    if not en_keys:
        return 0.0

    ru_tokens = {w.strip('.,!?;:—–()«»"\'').lower()
                 for w in ru_sentence.split()
                 if w.strip('.,!?;:—–()«»"\'').lower() not in _STOP_RU}

    matches = sum(
        1 for k in en_keys
        if any(k[:4] in rt for rt in ru_tokens)   # частичное совпадение по префиксу
    )
    return matches / len(en_keys)


# ── Расчёт смещения ───────────────────────────────────────────────────────────

def _compute_offset(conn, ru_text_id: int, translation_id: int):
    df = pd.read_sql_query(f"""
        SELECT se.position AS en_pos, sr.position AS ru_pos
        FROM alignment a
        JOIN sentences sr ON sr.sentence_id = a.sentence_ru_id
        JOIN sentences se ON se.sentence_id = a.sentence_en_id
        WHERE sr.text_id = {ru_text_id}
          AND se.translation_id = {translation_id}
    """, conn)
    if df.empty:
        return None, None
    offsets = df['en_pos'] - df['ru_pos']
    return float(np.median(offsets)), float(np.std(offsets))


# ── Основная функция ──────────────────────────────────────────────────────────

def review_unmatched(
    ru_text_id: int,
    translation_id: int,
    top_k: int = 3,
    use_position_window: bool = True,
    tolerance: int = 200,
):
    conn = sqlite3.connect(DB_PATH)

    df_ru = pd.read_sql_query(f"""
        SELECT sentence_id, position, sentence FROM sentences
        WHERE source_type='original' AND text_id={ru_text_id} AND language='ru'
        ORDER BY position
    """, conn)

    df_en_all = pd.read_sql_query(f"""
        SELECT sentence_id, position, sentence FROM sentences
        WHERE source_type='translation' AND translation_id={translation_id} AND language='en'
        ORDER BY position
    """, conn)

    matched_en = pd.read_sql_query(f"""
        SELECT DISTINCT a.sentence_en_id FROM alignment a
        JOIN sentences s ON s.sentence_id = a.sentence_ru_id
        WHERE s.text_id = {ru_text_id}
    """, conn)['sentence_en_id'].tolist()

    df_en = df_en_all[~df_en_all['sentence_id'].isin(matched_en)].reset_index(drop=True)

    print(f"\n📊 Непривязанных EN: {len(df_en)} из {len(df_en_all)}")
    print(f"   RU предложений: {len(df_ru)}")

    if df_en.empty:
        print("✅ Все EN-предложения уже привязаны.")
        conn.close()
        return

    # Смещение
    offset, offset_std = _compute_offset(conn, ru_text_id, translation_id)
    if use_position_window and offset is not None:
        print(f"\n📐 Смещение EN−RU: {offset:+.0f} предл. (σ={offset_std:.0f})")
        print(f"   Окно поиска: offset ± {tolerance} предл.")
    elif use_position_window:
        print("\n⚠️  Нет выровненных пар — поиск по всему тексту.")
        use_position_window = False

    # Кодирование LaBSE
    model = get_model()
    print("\n🔢 Кодирую предложения через LaBSE...")
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    en_vecs = model.encode(df_en["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    sim_matrix = _cosine_matrix(ru_vecs, en_vecs)  # (n_ru, n_en)

    # Позиционная маска по смещению
    if use_position_window and offset is not None:
        ru_pos      = df_ru["position"].values
        en_pos      = df_en["position"].values
        expected_ru = en_pos - offset          # (n_en,)
        pos_diff    = np.abs(ru_pos[:, None] - expected_ru[None, :])  # (n_ru, n_en)
        in_window   = pos_diff <= tolerance    # булева маска
    else:
        in_window = np.ones((len(df_ru), len(df_en)), dtype=bool)

    # Интерактивный обход
    cursor = conn.cursor()
    stats = {'confirmed': 0, 'skipped': 0}

    print(f"\n{'='*70}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(df_en)} предложений")
    print(f"   Управление: 1-{top_k} — принять | s — пропустить | q — выйти")
    print(f"{'='*70}\n")

    for j, en_row in df_en.iterrows():
        en_text = en_row['sentence']

        # Кандидаты в окне
        window_mask = in_window[:, j]
        if not window_mask.any():
            window_mask = np.ones(len(df_ru), dtype=bool)  # fallback — весь текст

        col_sim = sim_matrix[:, j].copy()
        col_sim[~window_mask] = 0.0

        # Лексический скор (транслитерация без перевода)
        lex_scores = np.array([
            word_overlap(en_text, df_ru.iloc[i]['sentence']) if window_mask[i] else 0.0
            for i in range(len(df_ru))
        ])

        hybrid = 0.5 * col_sim + 0.5 * lex_scores
        top_indices = np.argsort(hybrid)[::-1][:top_k]

        print(f"[{j+1}/{len(df_en)}] EN  (pos={en_row['position']}):")
        print(f"  \"{en_text[:120]}\"")
        print()

        candidates = []
        for rank, ru_i in enumerate(top_indices, 1):
            ru_row  = df_ru.iloc[ru_i]
            h_score = float(hybrid[ru_i])
            c_score = float(col_sim[ru_i])
            l_score = float(lex_scores[ru_i])
            candidates.append((ru_row, c_score))
            print(f"  [{rank}] hybrid={h_score:.3f}  (sim={c_score:.3f} + lex={l_score:.3f})  pos={ru_row['position']}")
            print(f"       \"{ru_row['sentence'][:120]}\"")
        print()

        while True:
            choice = input(f"  Выбор (1-{top_k} / s=пропустить / q=выйти): ").strip().lower()
            if choice == 'q':
                conn.commit()
                conn.close()
                print(f"\n✅ Прервано. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")
                return
            if choice == 's':
                stats['skipped'] += 1
                break
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                idx   = int(choice) - 1
                ru_row, sim = candidates[idx]
                ru_id = int(ru_row['sentence_id'])
                en_id = int(en_row['sentence_id'])

                existing = cursor.execute(
                    "SELECT alignment_id FROM alignment WHERE sentence_ru_id=? AND sentence_en_id=?",
                    (ru_id, en_id)).fetchone()

                if existing:
                    print("  ℹ️  Эта пара уже есть в БД.\n")
                else:
                    cursor.execute(
                        "INSERT INTO alignment (sentence_ru_id, sentence_en_id, cosine_sim, auto_aligned)"
                        " VALUES (?,?,?,0)",
                        (ru_id, en_id, round(sim, 4)))
                    stats['confirmed'] += 1
                    print(f"  ✅ Сохранено (sim={sim:.3f})\n")
                break
            print("  ❌ Неверный ввод.")

        print('-' * 70)

    conn.commit()
    conn.close()
    print(f"\n✅ ГОТОВО. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ru',        type=int, required=True)
    parser.add_argument('--en',        type=int, required=True)
    parser.add_argument('--top',       type=int, default=3)
    parser.add_argument('--tolerance', type=int, default=200)
    parser.add_argument('--no-window', action='store_true')
    args = parser.parse_args()

    review_unmatched(
        ru_text_id=args.ru,
        translation_id=args.en,
        top_k=args.top,
        use_position_window=not args.no_window,
        tolerance=args.tolerance,
    )


if __name__ == '__main__':
    main()
