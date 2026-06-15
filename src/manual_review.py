# src/manual_review.py
"""
Интерактивная проверка непривязанных EN-предложений.

Алгоритм:
  1. Перевод EN→RU (Helsinki-NLP/opus-mt-en-ru, локальная папка C:\models\opus-mt-en-ru).
  2. Гибридный скор = 0.5 × cosine_sim(LaBSE) + 0.5 × word_overlap(перевод, RU).
  3. Показывает топ-K кандидатов по всему тексту.
  4. Пользователь подтверждает, пропускает или ищет по ключевому слову (f).

Запуск:
    python src/manual_review.py --ru 1 --en 1
    python src/manual_review.py --ru 1 --en 1 --top 5
"""

import sqlite3
import argparse
import numpy as np
import pandas as pd

from config import DB_PATH
from auto_align import get_model, _cosine_matrix

# ── Перевод EN→RU ─────────────────────────────────────────────────────────────

_translator = None
_tok = None

# Путь к локальной копии модели Helsinki-NLP/opus-mt-en-ru
_OPUS_MT_PATH = r"C:\models\opus-mt-en-ru"

def _get_translator():
    global _translator, _tok
    if _translator is None:
        from transformers import MarianMTModel, MarianTokenizer
        import os
        print("🔄 Загружаю переводчик из локальной папки...")
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


def translate_en_ru(text: str) -> str:
    model, tok = _get_translator()
    inputs = tok([text], return_tensors="pt", padding=True, truncation=True, max_length=512)
    tokens = model.generate(**inputs)
    return tok.decode(tokens[0], skip_special_tokens=True)


# ── Лексический скоринг ───────────────────────────────────────────────────────

_STOP_RU = {'и', 'в', 'не', 'на', 'с', 'что', 'а', 'это', 'из', 'по', 'к', 'но',
            'он', 'она', 'они', 'мы', 'вы', 'я', 'его', 'её', 'их', 'как', 'или',
            'то', 'уже', 'всё', 'так', 'же', 'был', 'была', 'были', 'есть', 'за'}

def word_overlap(translated: str, candidate: str) -> float:
    def tokens(s):
        return {w.strip('.,!?;:—–()«»"\'') for w in s.lower().split()
                if len(w) > 2 and w not in _STOP_RU}
    t = tokens(translated)
    c = tokens(candidate)
    if not t:
        return 0.0
    return len(t & c) / len(t)


# ── Поиск по ключевому слову ─────────────────────────────────────────────────

def find_by_keyword(df_ru: pd.DataFrame, keyword: str) -> None:
    kw = keyword.lower()
    matches = df_ru[df_ru['sentence'].str.lower().str.contains(kw, na=False)]
    if matches.empty:
        print(f"  ❌ Ничего не найдено по слову «{keyword}»")
        return
    print(f"  🔍 Найдено {len(matches)} предложений:")
    for _, row in matches.iterrows():
        print(f"    pos={row['position']}  id={row['sentence_id']}")
        print(f"    \"{row['sentence'][:120]}\"")
    print()


# ── Сохранение пары ──────────────────────────────────────────────────────────

def _save_pair(cursor, ru_id: int, en_id: int, sim: float, stats: dict) -> None:
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


# ── Основная функция ──────────────────────────────────────────────────────────

def review_unmatched(ru_text_id: int, translation_id: int, top_k: int = 3):
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

    print("\n🔤 Загружаю переводчик...")
    _get_translator()

    model = get_model()
    print("\n🔢 Кодирую предложения через LaBSE...")
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    en_vecs = model.encode(df_en["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    sim_matrix = _cosine_matrix(ru_vecs, en_vecs)

    cursor = conn.cursor()
    stats = {'confirmed': 0, 'skipped': 0}

    print(f"\n{'='*70}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(df_en)} предложений")
    print(f"   Управление: 1-{top_k} — принять | f — найти по слову | s — пропустить | q — выйти")
    print(f"{'='*70}\n")

    for j, en_row in df_en.iterrows():
        en_text    = en_row['sentence']
        col_sim    = sim_matrix[:, j]
        translated = translate_en_ru(en_text)

        lex_scores = np.array([
            word_overlap(translated, df_ru.iloc[i]['sentence'])
            for i in range(len(df_ru))
        ])

        hybrid      = 0.5 * col_sim + 0.5 * lex_scores
        top_indices = np.argsort(hybrid)[::-1][:top_k]

        print(f"[{j+1}/{len(df_en)}] EN  (pos={en_row['position']}):")
        print(f"  \"{en_text[:120]}\"")
        print(f"  → RU: \"{translated[:120]}\"")
        print()

        candidates = []
        for rank, ru_i in enumerate(top_indices, 1):
            ru_row = df_ru.iloc[ru_i]
            h = float(hybrid[ru_i])
            c = float(col_sim[ru_i])
            l = float(lex_scores[ru_i])
            candidates.append((ru_row, c))
            print(f"  [{rank}] hybrid={h:.3f}  (sim={c:.3f} + lex={l:.3f})  pos={ru_row['position']}")
            print(f"       \"{ru_row['sentence'][:120]}\"")
        print()

        while True:
            choice = input(f"  Выбор (1-{top_k} / f=поиск / s=пропустить / q=выйти): ").strip().lower()

            if choice == 'q':
                conn.commit()
                conn.close()
                print(f"\n✅ Прервано. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")
                return

            if choice == 's':
                stats['skipped'] += 1
                break

            if choice == 'f':
                kw = input("  Ключевое слово: ").strip()
                find_by_keyword(df_ru, kw)
                # После поиска спрашиваем: ввести sentence_id вручную?
                sid = input("  Ввести sentence_id для сохранения (или Enter чтобы продолжить): ").strip()
                if sid.isdigit():
                    ru_id = int(sid)
                    row = df_ru[df_ru['sentence_id'] == ru_id]
                    if row.empty:
                        print("  ❌ sentence_id не найден.")
                    else:
                        sim = float(col_sim[row.index[0]])
                        _save_pair(cursor, ru_id, int(en_row['sentence_id']), sim, stats)
                        break
                continue

            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                idx = int(choice) - 1
                ru_row, sim = candidates[idx]
                _save_pair(cursor, int(ru_row['sentence_id']), int(en_row['sentence_id']), sim, stats)
                break

            print("  ❌ Неверный ввод.")

        print('-' * 70)

    conn.commit()
    conn.close()
    print(f"\n✅ ГОТОВО. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ru',  type=int, required=True)
    parser.add_argument('--en',  type=int, required=True)
    parser.add_argument('--top', type=int, default=3)
    args = parser.parse_args()

    review_unmatched(
        ru_text_id=args.ru,
        translation_id=args.en,
        top_k=args.top,
    )


if __name__ == '__main__':
    main()
