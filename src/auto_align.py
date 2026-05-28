# src/auto_align.py
"""
Автоматическое выравнивание ольфакторных предложений с помощью LaBSE.

Алгоритм:
  1. Загружаем RU и EN ольфакторные предложения из БД для указанной пары текстов.
  2. Кодируем оба набора мультиязычной моделью LaBSE — она строит вектора
     в общем пространстве для всех языков, поэтому косинусное сходство
     перевода и оригинала будет высоким.
  3. Позиционное окно (необязательно): нормализуем позиции предложений в тексте
     и допускаем только кандидатов, расположенных "рядом" по книге
     (|pos_ru_norm - pos_en_norm| <= window). Это отсекает семантически
     похожие, но далёкие по сюжету предложения.
  4. Для каждого RU предложения выбираем лучший EN кандидат.
     Если cosine_sim >= threshold — пишем пару в таблицу alignment.

Запуск:
    python src/auto_align.py --ru 1 --en 1
    python src/auto_align.py --ru 1 --en 1 --threshold 0.60 --no-window
    python src/auto_align.py --all               # все пары текстов в БД
"""

import sys
import sqlite3
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from config import DB_PATH

# ── Ленивая загрузка модели ───────────────────────────────────────────────────

_model = None

MODEL_NAME = "cointegrated/LaBSE-en-ru"
# Компактная (~500 MB) версия LaBSE, обученная специально на русско-английских парах.
# Уже скачана в кэш. Альтернатива: "LaBSE" (~1.7 GB, полная мультиязычная).


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print(f"🔄 Загружаю модель {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        print("✅ Модель загружена")
    return _model


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Матрица косинусного сходства (n_ru × n_en)."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return a_norm @ b_norm.T



# ── Основная функция ─────────────────────────────────────────────────────────

def auto_align_sentences(
    ru_text_id: int,
    translation_id: int,
    threshold: float = 0.65,
    use_position_window: bool = True,
    window_size: float = 0.12,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Автоматически выравнивает ольфакторные предложения для пары (RU текст, EN перевод).

    Параметры
    ----------
    ru_text_id       : ID русского текста в таблице texts
    translation_id   : ID английского перевода в таблице translations
    threshold        : минимальный cosine_sim для добавления пары (0..1)
    use_position_window : фильтровать кандидатов по близкой позиции в книге
    window_size      : ширина окна (доля от длины текста); 0.12 = ±12%
    skip_existing    : пропускать RU/EN предложения, уже занятые в alignment
    dry_run          : не записывать в БД, только показать результат

    Возвращает словарь со статистикой.
    """
    conn = sqlite3.connect(DB_PATH)

    # ── 1. Загрузка предложений ───────────────────────────────────────────────
    skip_ru_filter = ""
    skip_en_filter = ""
    if skip_existing:
        skip_ru_filter = "AND sentence_id NOT IN (SELECT sentence_ru_id FROM alignment WHERE sentence_ru_id IS NOT NULL)"
        skip_en_filter = "AND sentence_id NOT IN (SELECT sentence_en_id FROM alignment WHERE sentence_en_id IS NOT NULL)"

    df_ru = pd.read_sql_query(f"""
        SELECT sentence_id, position, sentence
        FROM sentences
        WHERE source_type = 'original'
          AND text_id = {ru_text_id}
          AND language = 'ru'
          {skip_ru_filter}
        ORDER BY position
    """, conn)

    df_en = pd.read_sql_query(f"""
        SELECT sentence_id, position, sentence
        FROM sentences
        WHERE source_type = 'translation'
          AND translation_id = {translation_id}
          AND language = 'en'
          {skip_en_filter}
        ORDER BY position
    """, conn)

    total_ru = conn.execute(
        "SELECT MAX(position) FROM sentences WHERE source_type='original' AND text_id=?",
        (ru_text_id,)
    ).fetchone()[0] or len(df_ru)

    total_en = conn.execute(
        "SELECT MAX(position) FROM sentences WHERE source_type='translation' AND translation_id=?",
        (translation_id,)
    ).fetchone()[0] or len(df_en)

    print(f"\n📊 Предложений для выравнивания:")
    print(f"   RU (text_id={ru_text_id}):  {len(df_ru)} ольфакторных из {total_ru} всего")
    print(f"   EN (translation_id={translation_id}): {len(df_en)} ольфакторных из {total_en} всего")

    if df_ru.empty or df_en.empty:
        print("⚠️  Нечего выравнивать.")
        conn.close()
        return {"inserted": 0, "skipped": 0, "below_threshold": 0}

    # ── 2. Кодирование с LaBSE ───────────────────────────────────────────────
    model = get_model()
    print("\n🔢 Кодирую предложения...")
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    en_vecs = model.encode(df_en["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)

    # ── 3. Матрица косинусного сходства ──────────────────────────────────────
    sim_matrix = _cosine_matrix(ru_vecs, en_vecs)  # shape: (n_ru, n_en)

    # ── 4. Позиционное окно ──────────────────────────────────────────────────
    if use_position_window:
        # Нормализуем по полной длине текста, а не по максимуму среди ольфакторных
        ru_pos = df_ru["position"].values / total_ru
        en_pos = df_en["position"].values / total_en
        # Матрица расстояний по позиции (n_ru × n_en)
        pos_diff = np.abs(ru_pos[:, None] - en_pos[None, :])
        # Обнуляем сходство для кандидатов вне окна
        sim_matrix = np.where(pos_diff <= window_size, sim_matrix, 0.0)
        print(f"   Позиционное окно: ±{window_size*100:.0f}% | RU всего предл.: {total_ru}, EN всего предл.: {total_en}")

    # ── 5. Лучший кандидат для каждого RU предложения ────────────────────────
    cursor = conn.cursor()
    stats = {"inserted": 0, "skipped": 0, "below_threshold": 0}
    pairs = []

    for i, ru_row in df_ru.iterrows():
        row_sims = sim_matrix[df_ru.index.get_loc(i)]  # сходства для RU[i]
        best_j = int(np.argmax(row_sims))
        best_sim = float(row_sims[best_j])

        if best_sim < threshold:
            stats["below_threshold"] += 1
            continue

        en_row = df_en.iloc[best_j]
        pairs.append({
            "ru_id": int(ru_row["sentence_id"]),
            "en_id": int(en_row["sentence_id"]),
            "sim": best_sim,
            "ru_text": ru_row["sentence"][:80],
            "en_text": en_row["sentence"][:80],
        })

    # ── 6. Запись в БД ────────────────────────────────────────────────────────
    print(f"\n{'🔍 DRY RUN — в БД не пишу' if dry_run else '💾 Записываю в БД...'}")
    print(f"{'─'*70}")

    for p in pairs:
        print(f"  sim={p['sim']:.3f} | {p['ru_text']}…")
        print(f"           → {p['en_text']}…")

        if not dry_run:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO alignment
                        (sentence_ru_id, sentence_en_id, cosine_sim, auto_aligned, verified)
                    VALUES (?, ?, ?, 1, 0)
                """, (p["ru_id"], p["en_id"], p["sim"]))
                stats["inserted"] += 1
            except Exception as e:
                print(f"   ⚠️  Ошибка: {e}")
                stats["skipped"] += 1
        else:
            stats["inserted"] += 1

    if not dry_run:
        conn.commit()

    conn.close()

    # ── 7. Итог ───────────────────────────────────────────────────────────────
    total = len(df_ru)
    print(f"\n{'='*60}")
    print("📊 РЕЗУЛЬТАТ АВТОВЫРАВНИВАНИЯ")
    print(f"{'='*60}")
    print(f"   Всего RU предложений: {total}")
    print(f"   {'Найдено бы' if dry_run else 'Добавлено'} пар:  {stats['inserted']}")
    print(f"   Ниже порога ({threshold}):  {stats['below_threshold']}")
    if stats["skipped"]:
        print(f"   Ошибок:         {stats['skipped']}")

    if total > 0:
        coverage = (stats["inserted"]) / total * 100
        print(f"   Покрытие:       {coverage:.1f}%")

    return stats


# ── Показать все доступные пары текст/перевод ─────────────────────────────────

def list_text_pairs(conn) -> pd.DataFrame:
    """Возвращает таблицу всех пар (RU оригинал, EN перевод) в БД."""
    df = pd.read_sql_query("""
        SELECT
            t.text_id,
            t.title        AS ru_title,
            t.author,
            tr.translation_id,
            tr.translator
        FROM translations tr
        JOIN texts t ON tr.text_id = t.text_id
        WHERE t.language = 'ru' AND tr.language = 'en'
        ORDER BY t.text_id, tr.translation_id
    """, conn)
    return df


# ── Точка входа ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Автовыравнивание через LaBSE")
    parser.add_argument("--ru",        type=int, help="text_id русского оригинала")
    parser.add_argument("--en",        type=int, help="translation_id английского перевода")
    parser.add_argument("--all",       action="store_true", help="Все пары текстов в БД")
    parser.add_argument("--threshold", type=float, default=0.65, help="Мин. cosine_sim (по умолч. 0.65)")
    parser.add_argument("--window",    type=float, default=0.12,  help="Ширина позиц. окна 0..1 (по умолч. 0.12)")
    parser.add_argument("--no-window", dest="use_window", action="store_false", help="Отключить позиционный фильтр")
    parser.add_argument("--dry-run",   action="store_true", help="Показать пары, не записывая в БД")
    parser.set_defaults(use_window=True)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    if args.all:
        pairs = list_text_pairs(conn)
        if pairs.empty:
            print("❌ Нет пар текст/перевод в БД")
            conn.close()
            return
        print("\n📚 Найденные пары:")
        print(pairs.to_string(index=False))
        conn.close()
        for _, row in pairs.iterrows():
            auto_align_sentences(
                ru_text_id=int(row["text_id"]),
                translation_id=int(row["translation_id"]),
                threshold=args.threshold,
                use_position_window=args.use_window,
                window_size=args.window,
                dry_run=args.dry_run,
            )

    elif args.ru and args.en:
        conn.close()
        auto_align_sentences(
            ru_text_id=args.ru,
            translation_id=args.en,
            threshold=args.threshold,
            use_position_window=args.use_window,
            window_size=args.window,
            dry_run=args.dry_run,
        )

    else:
        # Показываем список пар и просим выбрать
        pairs = list_text_pairs(conn)
        conn.close()
        if pairs.empty:
            print("❌ Нет пар текст/перевод в БД")
            return
        print("\n📚 Доступные пары текстов:")
        print(pairs.to_string(index=False))
        print("\nЗапустите с --ru <text_id> --en <translation_id>")
        print("  или --all для обработки всех пар")


if __name__ == "__main__":
    main()
