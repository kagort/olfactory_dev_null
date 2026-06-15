# src/manual_review.py
"""
Интерактивная проверка непривязанных EN-предложений.

Для каждого EN без пары LaBSE находит топ-3 RU-кандидата.
Пользователь подтверждает или пропускает.
Подтверждённые пары → alignment (auto_aligned=0, cosine_sim сохраняется).

Запуск:
    python src/manual_review.py --ru 1 --en 1
    python src/manual_review.py --ru 1 --en 1 --top 5
    python src/manual_review.py --ru 1 --en 1 --no-window
"""

import sys
import sqlite3
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

from config import DB_PATH
from auto_align import get_model, _cosine_matrix


def review_unmatched(
    ru_text_id: int,
    translation_id: int,
    top_k: int = 3,
    use_position_window: bool = True,
    window_size: float = 0.20,
):
    conn = sqlite3.connect(DB_PATH)

    # ── 1. Все ольфакторные предложения ──────────────────────────────────────
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

    # ── 2. Только EN без пары ─────────────────────────────────────────────────
    matched_en = pd.read_sql_query(f"""
        SELECT DISTINCT a.sentence_en_id FROM alignment a
        JOIN sentences s ON s.sentence_id = a.sentence_ru_id
        WHERE s.text_id = {ru_text_id}
    """, conn)['sentence_en_id'].tolist()

    df_en = df_en_all[~df_en_all['sentence_id'].isin(matched_en)].reset_index(drop=True)

    total_ru = conn.execute(
        "SELECT MAX(position) FROM sentences WHERE source_type='original' AND text_id=?",
        (ru_text_id,)).fetchone()[0] or len(df_ru)
    total_en = conn.execute(
        "SELECT MAX(position) FROM sentences WHERE source_type='translation' AND translation_id=?",
        (translation_id,)).fetchone()[0] or len(df_en_all)

    print(f"\n📊 Непривязанных EN: {len(df_en)} из {len(df_en_all)}")
    print(f"   RU предложений: {len(df_ru)}")

    if df_en.empty:
        print("✅ Все EN-предложения уже привязаны.")
        conn.close()
        return

    # ── 3. Кодирование ───────────────────────────────────────────────────────
    model = get_model()
    print("\n🔢 Кодирую предложения...")
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    en_vecs = model.encode(df_en["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)

    # sim_matrix: (n_ru × n_en)
    sim_matrix = _cosine_matrix(ru_vecs, en_vecs)

    # Позиционное окно
    if use_position_window:
        ru_pos = df_ru["position"].values / total_ru
        en_pos = df_en["position"].values / total_en
        pos_diff = np.abs(ru_pos[:, None] - en_pos[None, :])
        sim_matrix = np.where(pos_diff <= window_size, sim_matrix, 0.0)

    # ── 4. Интерактивный обход ────────────────────────────────────────────────
    cursor = conn.cursor()
    stats = {'confirmed': 0, 'skipped': 0}

    print(f"\n{'='*70}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(df_en)} предложений")
    print(f"   Управление: 1/2/3 — принять кандидата | s — пропустить | q — выйти")
    print(f"{'='*70}\n")

    for j, en_row in df_en.iterrows():
        col = sim_matrix[:, j]  # сходства всех RU с этим EN
        top_indices = np.argsort(col)[::-1][:top_k]

        print(f"[{j+1}/{len(df_en)}] EN  (pos={en_row['position']}):")
        print(f"  \"{en_row['sentence'][:120]}\"")
        print()

        candidates = []
        for rank, ru_i in enumerate(top_indices, 1):
            ru_row = df_ru.iloc[ru_i]
            sim = float(col[ru_i])
            candidates.append((ru_row, sim))
            sim_label = f"{sim:.3f}"
            print(f"  [{rank}] sim={sim_label}  (pos={ru_row['position']})")
            print(f"       \"{ru_row['sentence'][:120]}\"")
        print()

        while True:
            choice = input("  Выбор (1-3 / s=пропустить / q=выйти): ").strip().lower()
            if choice == 'q':
                conn.commit()
                conn.close()
                print(f"\n✅ Прервано. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")
                return
            if choice == 's':
                stats['skipped'] += 1
                break
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                idx = int(choice) - 1
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
                        "INSERT INTO alignment (sentence_ru_id, sentence_en_id, cosine_sim, auto_aligned) VALUES (?,?,?,0)",
                        (ru_id, en_id, round(sim, 4)))
                    stats['confirmed'] += 1
                    print(f"  ✅ Сохранено (sim={sim:.3f})\n")
                break
            print("  ❌ Неверный ввод.")

        print('-' * 70)

    conn.commit()
    conn.close()
    print(f"\n✅ ГОТОВО. Подтверждено: {stats['confirmed']}, пропущено: {stats['skipped']}")


def main():
    parser = argparse.ArgumentParser(description="Ручная проверка непривязанных EN-предложений")
    parser.add_argument('--ru',  type=int, required=True, help='text_id русского текста')
    parser.add_argument('--en',  type=int, required=True, help='translation_id перевода')
    parser.add_argument('--top', type=int, default=3,     help='Кол-во кандидатов (default: 3)')
    parser.add_argument('--no-window', action='store_true', help='Отключить позиционное окно')
    args = parser.parse_args()

    review_unmatched(
        ru_text_id=args.ru,
        translation_id=args.en,
        top_k=args.top,
        use_position_window=not args.no_window,
    )


if __name__ == '__main__':
    main()
