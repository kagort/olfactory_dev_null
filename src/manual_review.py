# src/manual_review.py
"""
Интерактивная проверка непривязанных EN-предложений.

Для каждого EN без пары LaBSE находит топ-3 RU-кандидата.
Диапазон поиска рассчитывается автоматически по смещению уже выровненных пар:
    offset = median(en_pos - ru_pos)  по существующим парам
    окно поиска = [en_pos - offset - tolerance, en_pos - offset + tolerance]

Пользователь подтверждает или пропускает.
Подтверждённые пары → alignment (auto_aligned=0, cosine_sim сохраняется).

Запуск:
    python src/manual_review.py --ru 1 --en 1
    python src/manual_review.py --ru 1 --en 1 --top 5
    python src/manual_review.py --ru 1 --en 1 --tolerance 300
    python src/manual_review.py --ru 1 --en 1 --no-window
"""

import sys
import sqlite3
import argparse
import numpy as np
import pandas as pd

from config import DB_PATH
from auto_align import get_model, _cosine_matrix


def _compute_offset(conn, ru_text_id: int, translation_id: int):
    """
    Вычисляет медианное смещение позиций EN−RU по уже выровненным парам.
    Возвращает (offset, std) — смещение и разброс.
    """
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


def review_unmatched(
    ru_text_id: int,
    translation_id: int,
    top_k: int = 3,
    use_position_window: bool = True,
    tolerance: int = 200,
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

    print(f"\n📊 Непривязанных EN: {len(df_en)} из {len(df_en_all)}")
    print(f"   RU предложений: {len(df_ru)}")

    if df_en.empty:
        print("✅ Все EN-предложения уже привязаны.")
        conn.close()
        return

    # ── 3. Вычисляем смещение по выровненным парам ───────────────────────────
    offset, offset_std = _compute_offset(conn, ru_text_id, translation_id)

    if use_position_window and offset is not None:
        print(f"\n📐 Смещение EN−RU: {offset:+.0f} предл. (σ={offset_std:.0f})")
        print(f"   Окно поиска: offset ± {tolerance} предл.")
    elif use_position_window:
        print("\n⚠️  Нет выровненных пар для расчёта смещения — поиск по всему тексту.")
        use_position_window = False

    # ── 4. Кодирование ───────────────────────────────────────────────────────
    model = get_model()
    print("\n🔢 Кодирую предложения...")
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    en_vecs = model.encode(df_en["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)

    # sim_matrix: (n_ru × n_en)
    sim_matrix = _cosine_matrix(ru_vecs, en_vecs)

    # ── 5. Позиционное окно по смещению ──────────────────────────────────────
    if use_position_window and offset is not None:
        ru_pos = df_ru["position"].values   # абсолютные позиции RU
        en_pos = df_en["position"].values   # абсолютные позиции EN

        # Ожидаемая RU-позиция для каждого EN: en_pos - offset
        expected_ru = en_pos - offset       # shape: (n_en,)

        # Матрица: |ru_pos[i] - expected_ru[j]| <= tolerance
        pos_diff = np.abs(ru_pos[:, None] - expected_ru[None, :])   # (n_ru, n_en)
        sim_matrix = np.where(pos_diff <= tolerance, sim_matrix, 0.0)

    # ── 6. Интерактивный обход ────────────────────────────────────────────────
    cursor = conn.cursor()
    stats = {'confirmed': 0, 'skipped': 0}

    print(f"\n{'='*70}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(df_en)} предложений")
    print(f"   Управление: 1-{top_k} — принять | s — пропустить | q — выйти")
    print(f"{'='*70}\n")

    for j, en_row in df_en.iterrows():
        col = sim_matrix[:, j]
        top_indices = np.argsort(col)[::-1][:top_k]
        best_sim = float(col[top_indices[0]]) if len(top_indices) else 0.0

        print(f"[{j+1}/{len(df_en)}] EN  (pos={en_row['position']}):")
        print(f"  \"{en_row['sentence'][:120]}\"")

        # Предупреждение если все кандидаты слабые
        if best_sim < 0.40:
            print(f"  ⚠️  Низкое сходство (max={best_sim:.3f}) — кандидаты ненадёжны")
        print()

        candidates = []
        for rank, ru_i in enumerate(top_indices, 1):
            ru_row = df_ru.iloc[ru_i]
            sim = float(col[ru_i])
            candidates.append((ru_row, sim))
            print(f"  [{rank}] sim={sim:.3f}  (pos={ru_row['position']})")
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


def main():
    parser = argparse.ArgumentParser(description="Ручная проверка непривязанных EN-предложений")
    parser.add_argument('--ru',        type=int, required=True, help='text_id русского текста')
    parser.add_argument('--en',        type=int, required=True, help='translation_id перевода')
    parser.add_argument('--top',       type=int, default=3,     help='Кол-во кандидатов (default: 3)')
    parser.add_argument('--tolerance', type=int, default=200,   help='Окно поиска ± предл. (default: 200)')
    parser.add_argument('--no-window', action='store_true',     help='Отключить позиционное окно')
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
