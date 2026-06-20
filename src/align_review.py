"""
Интерактивная ручная разметка непривязанных EN-предложений.
Гибридный подход: LaBSE сходство + лексическое совпадение (word overlap).

Алгоритм:
  1. Перевод EN→RU (Helsinki-NLP/opus-mt-en-ru)
  2. Гибридный скор = 0.5 × cosine_sim(LaBSE) + 0.5 × word_overlap(перевод, RU)
  3. Показывает топ-K кандидатов по гибридному скору
  4. Пользователь может:
     - выбрать кандидата по номеру (1, 2, 3...)
     - найти по ключевому слову (f)
     - добавить слово в словарь (a)
     - пропустить (s)
     - выйти (q)

Запуск:
    python src/manual_review_v2.py --ru 1 --en 1
    python src/manual_review_v2.py --ru 1 --en 1 --top 5
    python src/manual_review_v2.py --ru 1 --en 1 --parse
"""

import re
import sqlite3
import argparse
import numpy as np
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import syntok.segmenter as segmenter
import pandas as pd

from config import DB_PATH, OLFACTORY_WORDS
from grammar import extract_concept_phrase_ru, parse_ru, parse_to_json
from align_auto import get_model, _cosine_matrix

# ── Конфигурация ─────────────────────────────────────────────────────────────

_OPUS_MT_PATH = r"C:\models\opus-mt-en-ru"
_STOP_RU = {'и', 'в', 'не', 'на', 'с', 'что', 'а', 'это', 'из', 'по', 'к', 'но',
            'он', 'она', 'они', 'мы', 'вы', 'я', 'его', 'её', 'их', 'как', 'или',
            'то', 'уже', 'всё', 'так', 'же', 'был', 'была', 'были', 'есть', 'за'}

# ── Ленивая загрузка ─────────────────────────────────────────────────────────

_translator = None
_tok = None
_model = None
_morph = None

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

def _get_model():
    global _model
    if _model is None:
        _model = get_model()  # из auto_align
    return _model

def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph

def lemmatize(word: str) -> str:
    morph = _get_morph()
    return morph.parse(word.lower())[0].normal_form

# ── Перевод EN→RU (batch) ────────────────────────────────────────────────────

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

# ── Лексический скоринг ──────────────────────────────────────────────────────

def word_overlap(translated: str, candidate: str) -> float:
    """Jaccard-подобие между переведённым EN и RU предложением."""
    def tokens(s):
        return {w.strip('.,!?;:—–()«»"\'') for w in s.lower().split()
                if len(w) > 2 and w not in _STOP_RU}
    t = tokens(translated)
    c = tokens(candidate)
    if not t:
        return 0.0
    return len(t & c) / len(t)

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

# ── Построение индексов ─────────────────────────────────────────────────────

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

# ── Поиск кандидатов ─────────────────────────────────────────────────────────

def search_candidates(
    words: List[str],
    lemma_index: Dict[str, List[int]],
    form_index:  Dict[str, List[int]],
) -> List[Tuple[int, List[str]]]:
    """Возвращает [(position, [matched_words]), ...] по убыванию совпадений."""
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

# ── Вывод кандидата с контекстом ────────────────────────────────────────────

def print_candidate_with_context(
    position: int,
    matched_words: List[str],
    pos_to_sentence: Dict[int, str],
    all_positions: List[int],
    prefix: str = "  >>>",
):
    idx = all_positions.index(position) if position in all_positions else -1
    context_positions = all_positions[max(0, idx - 2): idx + 3] if idx >= 0 else [position]

    print(f"  ─────────────────────────────────────────")
    print(f"  pos={position}  [совпало: {', '.join(matched_words)}]")
    for p in context_positions:
        s = pos_to_sentence.get(p, "")
        if p != position:
            s = s[:120]
        pfx = prefix if p == position else "     "
        print(f"  {pfx} {s}")
    print()

# ── Добавление слова в словарь ──────────────────────────────────────────────

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

# ── Сохранение пары ──────────────────────────────────────────────────────────

def save_pair(
    cursor,
    ru_text_id: int,
    en_sentence_id: int,
    position: int,
    sentence: str,
    do_parse: bool,
    stats: Dict,
    en_text: str = "",
    sim: float = None,
):
    # Найти или создать sentence_id
    row = cursor.execute(
        "SELECT sentence_id FROM sentences WHERE text_id=? AND sentence=? AND source_type='original'",
        (ru_text_id, sentence)
    ).fetchone()

    if row:
        ru_id = row[0]
    else:
        # Извлекаем concept_phrase и gram_structure для новой записи
        smell_words = OLFACTORY_WORDS.get('ru', set())
        try:
            concept = extract_concept_phrase_ru(sentence, smell_words)
        except Exception:
            concept = None
        try:
            gram_structure = parse_ru(concept or sentence)
            gram_json = parse_to_json(gram_structure)
        except Exception:
            gram_structure, gram_json = None, None

        # Найти search_word (первое совпавшее ольфакторное слово)
        import pymorphy3
        morph = pymorphy3.MorphAnalyzer()
        search_word = None
        for w in sentence.split():
            clean = w.strip('.,!?;:—–()«»"\'').lower()
            if morph.parse(clean)[0].normal_form in smell_words or clean in smell_words:
                search_word = w.strip('.,!?;:—–()«»"\'')
                break

        cursor.execute(
            """INSERT INTO sentences
               (source_type, text_id, position, sentence, language,
                search_word, concept_phrase, gram_structure, gram_json)
               VALUES ('original', ?, ?, ?, 'ru', ?, ?, ?, ?)""",
            (ru_text_id, position, sentence, search_word, concept, gram_structure, gram_json)
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
           VALUES (?, ?, ?, 0, 1)""",
        (ru_id, en_sentence_id, round(sim, 4) if sim is not None else None)
    )
    cursor.connection.commit()
    stats["confirmed"] += 1
    sim_str = f", sim={sim:.3f}" if sim is not None else ""
    print(f"  ✅ Сохранено (ru_id={ru_id}, pos={position}{sim_str})\n")

# ── Поиск по ключевому слову ────────────────────────────────────────────────

def find_by_keyword(
    keyword: str,
    pos_to_sentence: Dict[int, str],
    all_positions: List[int],
    lemma_index: Dict[str, List[int]],
    form_index: Dict[str, List[int]],
):
    """Находит предложения по ключевому слову и показывает их с контекстом."""
    words = keyword.split()
    candidates = search_candidates(words, lemma_index, form_index)

    if not candidates:
        print(f"  ❌ Ничего не найдено по слову «{keyword}»")
        return []

    if len(candidates) > 20:
        print(f"  ⚠️  Найдено {len(candidates)} совпадений — слишком много. Уточните запрос.")
        for p, mw in candidates[:5]:
            print(f"    pos={p}: {pos_to_sentence.get(p, '')[:80]}")
        print(f"    ... и ещё {len(candidates)-5}")
        return []

    print(f"  🔍 Найдено {len(candidates)} предложений:")
    for p, mw in candidates:
        print_candidate_with_context(p, mw, pos_to_sentence, all_positions, prefix="  🔍")
    
    return candidates

# ── Основная функция ──────────────────────────────────────────────────────────

def review_unmatched(
    ru_text_id: int, 
    translation_id: int, 
    top_k: int = 5,
    do_parse: bool = False,
    hybrid_weight: float = 0.5  # вес для cosine_sim (1 - hybrid_weight для word_overlap)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Добавить колонку assisted если нет
    try:
        cursor.execute("ALTER TABLE alignment ADD COLUMN assisted INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

    # ── 1. Загрузка непривязанных EN предложений ────────────────────────────
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

    # ── 2. Загрузка RU предложений ──────────────────────────────────────────
    ru_rows = cursor.execute("""
        SELECT sentence_id, position, sentence
        FROM sentences
        WHERE text_id = ? AND source_type = 'original' AND language = 'ru'
        ORDER BY position
    """, (ru_text_id,)).fetchall()

    df_ru = pd.DataFrame(ru_rows, columns=['sentence_id', 'position', 'sentence'])
    print(f"   RU ольфакторных предложений: {len(df_ru)}")

    # ── 3. Сырой RU текст для индексов и контекста ──────────────────────────
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

    # ── 4. Перевод EN→RU ──────────────────────────────────────────────────────
    print("\n🔄 Перевожу EN→RU...")
    en_texts = [r[2] for r in en_rows]
    translations = translate_batch(en_texts)

    # ── 5. Кодирование для гибридного скора ─────────────────────────────────
    print("\n🔢 Кодирую предложения через LaBSE...")
    model = _get_model()
    
    # Кодируем все RU предложения (из sentences)
    ru_vecs = model.encode(df_ru["sentence"].tolist(), show_progress_bar=True, convert_to_numpy=True)
    
    # Кодируем переводы EN
    tr_vecs = model.encode(translations, show_progress_bar=True, convert_to_numpy=True)
    
    # Матрица сходства (n_ru × n_en)
    sim_matrix = _cosine_matrix(ru_vecs, tr_vecs)

    # ── 6. Подготовка к интерактивной сессии ──────────────────────────────
    stats = {"confirmed": 0, "skipped": 0}

    print(f"\n{'═'*70}")
    print(f"📝 РУЧНАЯ РАЗМЕТКА — {len(en_rows)} предложений")
    print(f"   Управление: 1-{top_k} — выбрать кандидата | f — поиск по слову")
    print(f"   a — добавить слово в словарь | s — пропустить | q — выйти")
    print(f"   Гибридный скор: {hybrid_weight*100:.0f}% LaBSE + {(1-hybrid_weight)*100:.0f}% лексика")
    print(f"{'═'*70}\n")

    # ── 7. Интерактивная разметка ───────────────────────────────────────────
    for idx, (en_id, en_pos, en_text) in enumerate(en_rows):
        translated = translations[idx]
        col_sim_col = sim_matrix[:, idx]  # сходство с каждым RU предложением

        # Вычисляем лексические скоры
        lex_scores = np.array([
            word_overlap(translated, df_ru.iloc[i]['sentence'])
            for i in range(len(df_ru))
        ])

        # Гибридный скор
        hybrid = hybrid_weight * col_sim_col + (1 - hybrid_weight) * lex_scores
        top_indices = np.argsort(hybrid)[::-1][:top_k]

        print(f"{'═'*70}")
        print(f"[{idx+1}/{len(en_rows)}] EN (pos={en_pos}):")
        print(f"  \"{en_text}\"")
        print(f"  → RU: \"{translated}\"")
        print()

        # Показываем топ-K кандидатов
        candidates = []
        print(f"  🏆 Топ-{top_k} кандидатов (гибридный скор):")
        for rank, ru_i in enumerate(top_indices, 1):
            ru_row = df_ru.iloc[ru_i]
            h = float(hybrid[ru_i])
            c = float(col_sim_col[ru_i])
            l = float(lex_scores[ru_i])
            candidates.append((ru_row, c, h))
            print(f"  [{rank}] hybrid={h:.3f}  (sim={c:.3f} + lex={l:.3f})  pos={ru_row['position']}")
            print(f"       \"{ru_row['sentence'][:120]}\"")
        print()

        # ── Интерактивный цикл для текущего EN ──────────────────────────────
        saved = False
        skipped = False
        
        while not saved and not skipped:
            choice = input(f"  Выбор (1-{top_k} / f=поиск / a=добавить слово / s=пропустить / q=выйти): ").strip().lower()

            if choice == 'q':
                print(f"\n✅ Прервано. Привязано: {stats['confirmed']}, пропущено: {stats['skipped']}, осталось: {len(en_rows)-idx-1}")
                conn.close()
                return

            if choice == 's':
                stats["skipped"] += 1
                skipped = True
                break

            if choice == 'a':
                word_to_add = input("  Слово для добавления в словарь: ").strip()
                lang_choice = input("  Язык (ru/en, Enter=ru): ").strip().lower() or 'ru'
                if word_to_add and lang_choice in ('ru', 'en'):
                    add_olfactory_word(word_to_add, lang=lang_choice)
                continue

            if choice == 'f':
                keyword = input("  Ключевое слово для поиска: ").strip()
                if not keyword:
                    continue
                
                found = find_by_keyword(
                    keyword, pos_to_sentence, all_positions, 
                    lemma_index, form_index
                )
                
                if found:
                    # Позволяем выбрать позицию из найденных
                    while True:
                        pos_choice = input("  Введите pos для сохранения (или Enter чтобы продолжить): ").strip()
                        if not pos_choice:
                            break
                        if pos_choice.isdigit():
                            pos = int(pos_choice)
                            if pos in pos_to_sentence:
                                sentence = pos_to_sentence[pos]
                                # Находим sim для этого предложения
                                ru_row = df_ru[df_ru['position'] == pos]
                                sim = float(ru_row['cosine_sim'].iloc[0]) if not ru_row.empty else None
                                save_pair(
                                    cursor, ru_text_id, en_id, pos, sentence, 
                                    do_parse, stats, en_text, sim
                                )
                                saved = True
                                break
                            else:
                                print(f"  ❌ Позиция {pos} не найдена.")
                        else:
                            print("  ❌ Введите число или Enter.")
                continue

            # Выбор кандидата по номеру
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                idx_choice = int(choice) - 1
                ru_row, sim, hybrid_score = candidates[idx_choice]
                save_pair(
                    cursor, ru_text_id, en_id, 
                    int(ru_row['position']), ru_row['sentence'],
                    do_parse, stats, en_text, sim
                )
                saved = True
                break

            print("  ❌ Неверный ввод.")

        print('-' * 70)

    # ── 8. Итоги ──────────────────────────────────────────────────────────────
    conn.commit()
    conn.close()
    
    print(f"\n{'═'*70}")
    print(f"✅ СЕССИЯ ЗАВЕРШЕНА")
    print(f"{'═'*70}")
    print(f"   Привязано:  {stats['confirmed']}")
    print(f"   Пропущено:  {stats['skipped']}")
    print(f"   Осталось:   {len(en_rows) - stats['confirmed'] - stats['skipped']}")
    
    if _added_words:
        print(f"\n📖 Добавлено в словарь: {', '.join(_added_words)}")
        print(f"   Запустите 'python run.py detect --clear' и 'python run.py auto-align' для обновления.")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ручная разметка с гибридным скором")
    parser.add_argument('--ru', type=int, required=True, help='text_id русского текста')
    parser.add_argument('--en', type=int, required=True, help='translation_id английского перевода')
    parser.add_argument('--top', type=int, default=5, help='Количество кандидатов для показа (по умолч. 5)')
    parser.add_argument('--parse', action='store_true', help='Парсить грамматику при создании новых предложений')
    parser.add_argument('--weight', type=float, default=0.5, 
                       help='Вес LaBSE в гибридном скоре (0-1, по умолч. 0.5)')
    args = parser.parse_args()

    review_unmatched(
        ru_text_id=args.ru,
        translation_id=args.en,
        top_k=args.top,
        do_parse=args.parse,
        hybrid_weight=args.weight
    )

if __name__ == '__main__':
    main()