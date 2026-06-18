# src/processing.py
"""
Поиск ольфакторных предложений в текстах и переводах
Запуск:
    python src/processing.py
    python src/processing.py --clear
"""

import sys
import sqlite3
import re
import syntok.segmenter as segmenter
import spacy
import pymorphy3
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# # Добавляем корень проекта в путь
# sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, OLFACTORY_WORDS
from grammar import parse_ru, parse_en, parse_to_json, extract_concept_phrase_ru, extract_concept_phrase_en

_nlp_cache = {}
_morph_ru = None


def get_morph_ru() -> pymorphy3.MorphAnalyzer:
    global _morph_ru
    if _morph_ru is None:
        _morph_ru = pymorphy3.MorphAnalyzer()
    return _morph_ru


def lemmatize_ru(word: str) -> str:
    """Возвращает нормальную форму русского слова через pymorphy3."""
    return get_morph_ru().parse(word)[0].normal_form


def get_nlp_model(language: str):
    """Ленивая загрузка модели spaCy"""
    if language not in _nlp_cache:
        model_map = {'ru': 'ru_core_news_sm', 'en': 'en_core_web_sm'}
        _nlp_cache[language] = spacy.load(model_map[language])
    return _nlp_cache[language]


def split_sentences(text: str) -> List[str]:
    """Разбивает текст на предложения"""
    sentences = []
    for paragraph in segmenter.process(text):
        for sentence in paragraph:
            sent_text = ' '.join([token.value for token in sentence])
            sent_text = re.sub(r'\s+', ' ', sent_text).strip()
            if sent_text:
                sentences.append(sent_text)
    return sentences


def extract_context(words: List[str], word_pos: int, window: int = 3) -> Tuple[str, str]:
    """Извлекает левый и правый контекст (±window слов)."""
    left_start = max(0, word_pos - window)
    left_context = ' '.join(words[left_start:word_pos])

    right_end = min(len(words), word_pos + window + 1)
    right_context = ' '.join(words[word_pos + 1:right_end])

    return left_context, right_context


def _has_smell_word_ru(sentence: str, smell_words: set) -> bool:
    """Быстрая предпроверка для русского: лемматизирует каждый токен через pymorphy3."""
    for raw_word in re.findall(r'[а-яёА-ЯЁ]+', sentence.lower()):
        if lemmatize_ru(raw_word) in smell_words or raw_word in smell_words:
            return True
    return False


def analyze_sentence(sentence: str, position: int, language: str) -> Optional[Dict]:
    """Анализирует предложение, находит слова-запахи"""
    smell_words = OLFACTORY_WORDS.get(language, set())
    if not smell_words:
        return None

    # Предпроверка: для русского используем pymorphy3, для остальных — подстрока
    if language == 'ru':
        if not _has_smell_word_ru(sentence, smell_words):
            return None
    else:
        if not any(word in sentence.lower() for word in smell_words):
            return None

    nlp = get_nlp_model(language)
    doc = nlp(sentence)
    words = sentence.split()

    found_smells = []
    for token in doc:
        # Для русского добавляем pymorphy3-лемму как третий источник
        if language == 'ru':
            morph_lemma = lemmatize_ru(token.text.lower())
            match = (
                morph_lemma in smell_words
                or token.lemma_.lower() in smell_words
                or token.text.lower() in smell_words
            )
        else:
            match = token.lemma_.lower() in smell_words or token.text.lower() in smell_words

        if match:
            left, right = extract_context(words, token.i)
            found_smells.append({
                'word': token.text,
                'lemma': token.lemma_,
                'pos': token.pos_,
                'left_context': left,
                'right_context': right,
            })

    if not found_smells:
        return None

    first = found_smells[0]

    # Извлекаем концептуальную синтагму через dependency tree
    try:
        if language == 'ru':
            concept = extract_concept_phrase_ru(sentence, smell_words)
        else:
            concept = extract_concept_phrase_en(sentence, smell_words)
    except Exception:
        concept = sentence  # fallback

    try:
        gram = parse_ru(concept) if language == 'ru' else parse_en(concept)
    except Exception:
        gram = None

    return {
        'position': position,
        'sentence': sentence,
        'smell_words': found_smells,
        'search_word': first['word'],
        'left_context': first['left_context'],
        'right_context': first['right_context'],
        'concept_phrase': concept,
        'gram_structure': gram,
        'gram_json': parse_to_json(gram),
    }


def process_all_texts(clear_all: bool = False):
    """Обрабатывает все тексты и переводы"""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if clear_all:
        cursor.execute("DELETE FROM sentences")
        conn.commit()
        print("🗑️ Таблица sentences полностью очищена")

    stats = {
        'total': 0,
        'olfactory': 0,
        'originals': 0,
        'translations': 0
    }

    # 1. Обработка оригиналов
    print("\n📖 Обработка оригиналов...")
    cursor.execute("SELECT text_id, title, language, content FROM texts WHERE content IS NOT NULL")

    for text_id, title, lang, content in cursor.fetchall():
        print(f"   📕 {title} ({lang})")
        stats['originals'] += 1

        sentences = split_sentences(content)
        stats['total'] += len(sentences)

        found = 0
        for pos, sentence in enumerate(sentences, 1):
            result = analyze_sentence(sentence, pos, lang)
            if result:
                cursor.execute("""
                    INSERT INTO sentences
                    (source_type, text_id, translation_id, language, position,
                     sentence, search_word, left_context, right_context, concept_phrase,
                     syntax_tree, pos_tags, gram_structure, gram_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'original', text_id, None, lang, pos,
                    result['sentence'], result['search_word'],
                    result['left_context'], result['right_context'], result['concept_phrase'],
                    None,
                    json.dumps([w['pos'] for w in result['smell_words']]),
                    result['gram_structure'],
                    result['gram_json'],
                ))
                found += 1
                stats['olfactory'] += 1

        if found:
            print(f"      🔍 Найдено: {found}")
        conn.commit()

    # 2. Обработка переводов
    print("\n📖 Обработка переводов...")
    cursor.execute("SELECT translation_id, title, language, content FROM translations WHERE content IS NOT NULL")

    for trans_id, title, lang, content in cursor.fetchall():
        print(f"   📘 {title} ({lang})")
        stats['translations'] += 1

        sentences = split_sentences(content)
        stats['total'] += len(sentences)

        found = 0
        for pos, sentence in enumerate(sentences, 1):
            result = analyze_sentence(sentence, pos, lang)
            if result:
                cursor.execute("""
                    INSERT INTO sentences
                    (source_type, text_id, translation_id, language, position,
                     sentence, search_word, left_context, right_context, concept_phrase,
                     syntax_tree, pos_tags, gram_structure, gram_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'translation', None, trans_id, lang, pos,
                    result['sentence'], result['search_word'],
                    result['left_context'], result['right_context'], result['concept_phrase'],
                    None,
                    json.dumps([w['pos'] for w in result['smell_words']]),
                    result['gram_structure'],
                    result['gram_json'],
                ))
                found += 1
                stats['olfactory'] += 1

        if found:
            print(f"      🔍 Найдено: {found}")
        conn.commit()

    conn.close()

    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТЫ ОБРАБОТКИ")
    print("="*60)
    print(f"   Обработано оригиналов: {stats['originals']}")
    print(f"   Обработано переводов: {stats['translations']}")
    print(f"   Всего предложений: {stats['total']}")
    print(f"   Ольфакторных предложений: {stats['olfactory']}")

    if stats['total']:
        percent = stats['olfactory'] / stats['total'] * 100
        print(f"   Процент: {percent:.1f}%")


def parse_gram_structures():
    """
    Пересчитывает concept_phrase, gram_structure и gram_json для всех
    предложений в БД, используя корректное поддерево dependency parse.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT sentence_id, language, sentence FROM sentences WHERE sentence IS NOT NULL")
    rows = cursor.fetchall()
    print(f"\n🔍 Пересчёт concept_phrase + gram_structure для {len(rows)} предложений...")

    smell_words_ru = OLFACTORY_WORDS.get('ru', set())
    smell_words_en = OLFACTORY_WORDS.get('en', set())

    updated = 0
    for sentence_id, lang, sentence in rows:
        try:
            smell_words = smell_words_ru if lang == 'ru' else smell_words_en
            if lang == 'ru':
                concept = extract_concept_phrase_ru(sentence, smell_words)
            else:
                concept = extract_concept_phrase_en(sentence, smell_words)
            gram = parse_ru(concept) if lang == 'ru' else parse_en(concept)
            gram_j = parse_to_json(gram)
            cursor.execute(
                "UPDATE sentences SET concept_phrase=?, gram_structure=?, gram_json=? WHERE sentence_id=?",
                (concept, gram, gram_j, sentence_id)
            )
            updated += 1
        except Exception as e:
            print(f"   ⚠️  sentence_id={sentence_id}: {e}")

        if updated % 50 == 0 and updated:
            conn.commit()
            print(f"   {updated}/{len(rows)}", end="\r", flush=True)

    conn.commit()
    conn.close()
    print(f"   ✅ Обновлено: {updated} из {len(rows)}")


if __name__ == "__main__":
    if '--parse-only' in sys.argv:
        parse_gram_structures()
    else:
        clear = '--clear' in sys.argv
        process_all_texts(clear_all=clear)
