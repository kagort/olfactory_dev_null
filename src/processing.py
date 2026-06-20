"""
Поиск ольфакторных предложений в текстах и переводах
Запуск:
    python src/processing.py                        # обработать всё
    python src/processing.py --clear               # очистить и обработать всё
    python src/processing.py --text 1              # обработать только текст с id=1
    python src/processing.py --translation 2       # обработать только перевод с id=2
    python src/processing.py --text 1 --clear     # очистить и обработать текст 1
    
    # РЕЖИМ ПЕРЕСЧЁТА ГРАММАТИКИ
    python src/processing.py --parse-only          # пересчитать грамматику для пустых полей
    python src/processing.py --parse-only --force  # пересчитать грамматику для ВСЕХ предложений
    python src/processing.py --parse-only --sentence 42  # пересчитать для конкретного предложения
    python src/processing.py --parse-only --text 1 --force  # пересчитать для текста 1
    python src/processing.py --parse-only --translation 2 --force  # пересчитать для перевода 2
    python src/processing.py --parse-only --limit 100  # не более 100 предложений
    python src/processing.py --parse-only --lang ru  # только русские предложения
"""

import sqlite3
import argparse
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import syntok.segmenter as segmenter
import spacy
import pymorphy3

from tqdm import tqdm

from config import DB_PATH, OLFACTORY_WORDS
from grammar import parse_ru, parse_en, parse_to_json, extract_concept_phrase_ru, extract_concept_phrase_en

_nlp_cache = {}
_morph_ru = None

COMMIT_EVERY = 50

# ── Утилиты ──────────────────────────────────────────────────────────────────

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
    """Анализирует предложение, находит слова-запахи и вычисляет грамматику"""
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

    # Парсим грамматику
    try:
        gram = parse_ru(concept) if language == 'ru' else parse_en(concept)
        gram_json = parse_to_json(gram)
    except Exception:
        gram = None
        gram_json = None

    return {
        'position': position,
        'sentence': sentence,
        'smell_words': found_smells,
        'search_word': first['word'],
        'left_context': first['left_context'],
        'right_context': first['right_context'],
        'concept_phrase': concept,
        'gram_structure': gram,
        'gram_json': gram_json,
    }


# ── Универсальная функция обработки источника ─────────────────────────────

def process_source(
    cursor,
    source_type: str,  # 'original' или 'translation'
    source_id: int,    # text_id или translation_id
    title: str,
    lang: str,
    content: str,
    clear: bool = False,
    stats: dict = None
) -> dict:
    """
    Универсальная обработка источника (текста или перевода).
    
    source_type: 'original' или 'translation'
    source_id: text_id или translation_id соответственно
    """
    if stats is None:
        stats = {'total': 0, 'olfactory': 0}
    
    # Если нужно очистить — удаляем старые предложения для этого источника
    if clear:
        if source_type == 'original':
            cursor.execute("DELETE FROM sentences WHERE text_id = ?", (source_id,))
        else:  # translation
            cursor.execute("DELETE FROM sentences WHERE translation_id = ?", (source_id,))
        print(f"   🗑️ Очищены старые предложения для {title}")
    
    sentences = split_sentences(content)
    stats['total'] += len(sentences)
    found = 0
    
    # Определяем, какой ID вставлять (выносим за цикл для оптимизации)
    text_id = source_id if source_type == 'original' else None
    translation_id = source_id if source_type == 'translation' else None
    
    for pos, sentence in tqdm(enumerate(sentences, 1), total=len(sentences), desc=f"  {title[:30]}"):

        result = analyze_sentence(sentence, pos, lang)
        if result:
            cursor.execute("""
                INSERT INTO sentences
                (source_type, text_id, translation_id, language, position,
                 sentence, search_word, left_context, right_context, concept_phrase,
                 pos_tags, gram_structure, gram_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_type, text_id, translation_id, lang, pos,
                result['sentence'], result['search_word'],
                result['left_context'], result['right_context'], result['concept_phrase'],
                json.dumps([w['pos'] for w in result['smell_words']]),
                result['gram_structure'],
                result['gram_json'],
            ))
            
            found += 1
            stats['olfactory'] += 1
    
    if found:
        print(f"      🔍 Найдено: {found}")
    
    return stats


# ── Основная логика обработки ─────────────────────────────────────────────

def process_all_texts(
    text_id: Optional[int] = None,
    translation_id: Optional[int] = None,
    clear: bool = False
):
    """
    Обрабатывает тексты.
    
    - text_id=None, translation_id=None → обработать всё
    - text_id=1 → обработать только текст с id=1
    - translation_id=2 → обработать только перевод с id=2
    - clear=True → удалить старые данные перед обработкой
    """
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    stats = {
        'total': 0,
        'olfactory': 0,
        'originals': 0,
        'translations': 0
    }
    
    # Если указан конкретный перевод
    if translation_id is not None:
        print(f"\n📖 Обработка перевода с translation_id={translation_id}...")
        row = cursor.execute(
            "SELECT translation_id, title, language, content FROM translations WHERE translation_id = ?",
            (translation_id,)
        ).fetchone()
        if row:
            trans_id, title, lang, content = row
            print(f"   📘 {title} ({lang})")
            stats['translations'] += 1
            stats = process_source(
                cursor, 'translation', trans_id, title, lang, content, clear, stats
            )
            conn.commit()
        else:
            print(f"   ❌ Перевод с id={translation_id} не найден")
        conn.close()
        return stats
    
    # Если указан конкретный текст
    if text_id is not None:
        print(f"\n📖 Обработка текста с text_id={text_id}...")
        row = cursor.execute(
            "SELECT text_id, title, language, content FROM texts WHERE text_id = ?",
            (text_id,)
        ).fetchone()
        if row:
            tid, title, lang, content = row
            print(f"   📕 {title} ({lang})")
            stats['originals'] += 1
            stats = process_source(
                cursor, 'original', tid, title, lang, content, clear, stats
            )
            conn.commit()
        else:
            print(f"   ❌ Текст с id={text_id} не найден")
        conn.close()
        return stats
    
    # Если ничего не указано — обрабатываем всё
    if clear:
        cursor.execute("DELETE FROM sentences")
        conn.commit()
        print("🗑️ Таблица sentences полностью очищена")
    
    # 1. Обработка оригиналов
    print("\n📖 Обработка оригиналов...")
    cursor.execute("SELECT text_id, title, language, content FROM texts WHERE content IS NOT NULL")
    
    for tid, title, lang, content in cursor.fetchall():
        print(f"   📕 {title} ({lang})")
        stats['originals'] += 1
        stats = process_source(cursor, 'original', tid, title, lang, content, False, stats)
        conn.commit()
    
    # 2. Обработка переводов
    print("\n📖 Обработка переводов...")
    cursor.execute("SELECT translation_id, title, language, content FROM translations WHERE content IS NOT NULL")
    
    for trans_id, title, lang, content in cursor.fetchall():
        print(f"   📘 {title} ({lang})")
        stats['translations'] += 1
        stats = process_source(cursor, 'translation', trans_id, title, lang, content, False, stats)
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
    
    return stats


# ── Режим только парсинга ──────────────────────────────────────────────────

def parse_only_mode(
    text_id: Optional[int] = None,
    translation_id: Optional[int] = None,
    limit: Optional[int] = None,
    force: bool = False,
    sentence_id: Optional[int] = None,
    language: Optional[str] = None
):
    """
    Пересчитывает грамматику для существующих предложений.
    
    - text_id=None, translation_id=None → пересчитать для всех
    - text_id=1 → только для текста 1
    - translation_id=2 → только для перевода 2
    - sentence_id=42 → только для конкретного предложения
    - limit=100 → не более 100 предложений
    - force=True → пересчитать ВСЕ предложения (даже если грамматика уже есть)
    - language='ru' → только русские предложения
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Строим запрос
    query = """
        SELECT sentence_id, language, concept_phrase 
        FROM sentences 
        WHERE concept_phrase IS NOT NULL
    """
    params = []
    
    # Если force=False, пересчитываем только те, где грамматика пустая
    if not force:
        query += " AND (gram_structure IS NULL OR gram_structure = '')"
    
    # Фильтры
    if sentence_id is not None:
        query += " AND sentence_id = ?"
        params.append(sentence_id)
    elif text_id is not None:
        query += " AND text_id = ?"
        params.append(text_id)
    elif translation_id is not None:
        query += " AND translation_id = ?"
        params.append(translation_id)
    
    # Фильтр по языку
    if language is not None:
        query += " AND language = ?"
        params.append(language)
    
    query += " ORDER BY sentence_id"
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    if not rows:
        print("⚠️ Нет предложений для пересчёта грамматики")
        if not force:
            print("💡 Попробуйте с флагом --force, чтобы пересчитать все предложения")
        conn.close()
        return
    
    print(f"\n🔍 Пересчёт грамматики для {len(rows)} предложений...")
    if force:
        print("   (принудительный режим: пересчитываются все предложения)")
    if language:
        print(f"   (только язык: {language})")
    
    updated = 0
    for i, (sentence_id, lang, concept_phrase) in enumerate(rows, 1):
        print(f"\r   {i}/{len(rows)}", end="", flush=True)
        
        try:
            if lang == 'ru':
                gram = parse_ru(concept_phrase)
                gram_json = json.dumps(parse_to_json(gram), ensure_ascii=False)
                cursor.execute(
                    "UPDATE sentences SET gram_structure = ?, gram_json = ? WHERE sentence_id = ?",
                    (gram, gram_json, sentence_id)
                )
            else:  # en
                gram = parse_en(concept_phrase)
                cursor.execute(
                    "UPDATE sentences SET gram_structure = ? WHERE sentence_id = ?",
                    (gram, sentence_id)
                )
            updated += 1
        except Exception as e:
            print(f"\n   ⚠️  sentence_id={sentence_id}: {e}")
        
        if i % COMMIT_EVERY == 0:
            conn.commit()
    
    conn.commit()
    conn.close()
    print(f"\n   ✅ Обновлено: {updated} из {len(rows)}")


# ── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Поиск ольфакторных предложений")
    
    # Основные параметры
    parser.add_argument('--clear', action='store_true', help='Очистить таблицу sentences перед обработкой')
    parser.add_argument('--text', type=int, help='Обработать только текст с указанным text_id')
    parser.add_argument('--translation', type=int, help='Обработать только перевод с указанным translation_id')
    
    # Режим только парсинга
    parser.add_argument('--parse-only', action='store_true', help='Только пересчитать грамматику')
    parser.add_argument('--force', action='store_true', help='Принудительно пересчитать все предложения (даже если грамматика есть)')
    parser.add_argument('--sentence', type=int, help='Пересчитать грамматику для конкретного предложения по ID')
    parser.add_argument('--limit', type=int, help='Максимум предложений для пересчёта (с --parse-only)')
    parser.add_argument('--lang', type=str, choices=['ru', 'en'], help='Пересчитать только для указанного языка (ru/en)')
    
    args = parser.parse_args()
    
    if args.parse_only:
        parse_only_mode(
            text_id=args.text,
            translation_id=args.translation,
            limit=args.limit,
            force=args.force,
            sentence_id=args.sentence,
            language=args.lang
        )
    else:
        process_all_texts(
            text_id=args.text,
            translation_id=args.translation,
            clear=args.clear
        )