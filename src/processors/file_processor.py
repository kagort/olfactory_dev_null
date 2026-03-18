import re
import syntok.segmenter as segmenter
import spacy
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Кэш для моделей spaCy
_nlp_cache = {}

# Словарь запахов
OLFACTORY_WORDS = {
    'ru': {
        'запах', 'аромат', 'вонь', 'смрад', 'благоухание',
        'пахнуть', 'благоухать', 'вонять', 'смердеть',
        'душистый', 'пахучий', 'ароматный', 'душок', 'запашок',
        'пахнет', 'пахнут', 'пахло', 'пахла', 'пахли',
        'воняет', 'воняло', 'воняли', 'благоухает', 'благоухали'
    },
    'en': {
        'smell', 'scent', 'odor', 'fragrance', 'stench',
        'aroma', 'perfume', 'stink', 'reek', 'whiff',
        'smelled', 'smelt', 'scented', 'fragrant', 'odorous'
    }
}


class FileProcessor:
    def __init__(self, db):
        self.db = db
        self.supported_languages = ['ru', 'en']
        print("✅ FileProcessor инициализирован")
    
    def _get_nlp_model(self, language: str):
        """Загружает модель spaCy (лениво)"""
        if language not in _nlp_cache:
            model_map = {
                'ru': 'ru_core_news_sm',
                'en': 'en_core_web_sm'
            }
            model_name = model_map[language]
            print(f"🔄 Загрузка модели {model_name}...")
            _nlp_cache[language] = spacy.load(model_name)
            print(f"✅ Модель загружена")
        return _nlp_cache[language]
    
    def _detect_language(self, text: str) -> str:
        """Определяет язык текста"""
        sample = text[:1000].lower()
        if any('а' <= c <= 'я' for c in sample):
            return 'ru'
        return 'en'
    
    def _split_sentences(self, text: str) -> List[str]:
        """Разбивает текст на предложения"""
        sentences = []
        for paragraph in segmenter.process(text):
            for sentence in paragraph:
                sent_text = ' '.join([token.value for token in sentence])
                sent_text = re.sub(r'\s+', ' ', sent_text).strip()
                if sent_text:
                    sentences.append(sent_text)
        return sentences
    
    def _extract_context(self, words: List[str], word_pos: int, window: int = 3) -> Tuple[str, str, str]:
        """Извлекает левый контекст, правый контекст и словосочетание"""
        left_start = max(0, word_pos - window)
        left_end = word_pos
        right_start = word_pos + 1
        right_end = min(len(words), word_pos + window + 1)
        
        left_context = ' '.join(words[left_start:left_end])
        right_context = ' '.join(words[right_start:right_end])
        concept_phrase = ' '.join(words[left_start:right_end])
        
        return left_context, right_context, concept_phrase
    
    def _analyze_sentence(self, sentence: str, text_id: int, position: int, 
                          language: str) -> Optional[Dict]:
        """
        Анализирует предложение и возвращает данные для сохранения,
        если в нем есть запахи
        """
        smell_words = OLFACTORY_WORDS.get(language, set())
        if not smell_words:
            return None
        
        # Быстрая проверка: есть ли вообще запах в предложении
        if not any(word in sentence.lower() for word in smell_words):
            return None
        
        # Если есть - делаем глубокий анализ через spaCy
        nlp = self._get_nlp_model(language)
        doc = nlp(sentence)
        words = sentence.split()
        
        # Собираем все найденные слова-запахи
        found_smells = []
        
        for token in doc:
            if (token.lemma_.lower() in smell_words or 
                token.text.lower() in smell_words):
                
                left, right, concept = self._extract_context(words, token.i)
                
                found_smells.append({
                    'word': token.text,
                    'lemma': token.lemma_,
                    'pos': token.pos_,
                    'position': token.i + 1,
                    'left_context': left,
                    'right_context': right,
                    'concept': concept
                })
        
        if not found_smells:
            return None
        
        # Для всего предложения берем контекст первого найденного слова
        # (можно потом уточнить, но для начала сойдет)
        first = found_smells[0]
        
        return {
            'text_id': text_id,
            'position': position,
            'sentence': sentence,
            'smell_words': found_smells,  # список всех слов-запахов в предложении
            'left_context': first['left_context'],
            'right_context': first['right_context']
        }
    
    def process_file(self, file_path: str, 
                    title: Optional[str] = None,
                    author: Optional[str] = None,
                    year: Optional[int] = None,
                    language: Optional[str] = None,
                    is_original: bool = True,
                    original_lang: Optional[str] = None,
                    original_id: Optional[int] = None) -> Dict:
        """
        Обрабатывает файл: сохраняет текст и находит ольфакторные предложения
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        # Читаем файл
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Определяем язык
        if not language:
            language = self._detect_language(text)
        
        # Название из имени файла
        if not title:
            title = file_path.stem
        
        print(f"\n📖 Файл: {file_path.name}")
        print(f"📏 Размер: {len(text)} символов")
        print(f"📌 Язык: {language}")
        
        # Сохраняем текст в БД
        if is_original:
            text_id = self.db.texts.add_original(
                language=language,
                title=title,
                author=author if author else "Неизвестен",
                year=year,
                content=text
            )
            print(f"✅ Оригинал сохранен (ID: {text_id})")
        else:
            text_id = self.db.texts.add_translation(
                language=language,
                title=title,
                author=author if author else "Неизвестен",
                year=year,
                content=text,
                original_lang=original_lang,
                original_id=original_id
            )
            print(f"✅ Перевод сохранен (ID: {text_id})")
        
        # Разбиваем на предложения
        print("🔄 Разбиение на предложения...")
        sentences = self._split_sentences(text)
        print(f"📝 Всего предложений: {len(sentences)}")
        
        # Анализируем каждое предложение
        print("🔄 Поиск предложений с запахами...")
        olfactory_sentences = []
        
        for pos, sentence in enumerate(sentences, 1):
            result = self._analyze_sentence(sentence, text_id, pos, language)
            if result:
                olfactory_sentences.append(result)
        
        print(f"🔍 Найдено предложений с запахами: {len(olfactory_sentences)}")
        
        # Сохраняем найденные предложения в БД
        if olfactory_sentences:
            print("🔄 Сохранение результатов...")
            for olf_data in olfactory_sentences:
                self.db.olfactory.add(
                    language=language,
                    text_id=text_id,
                    position=olf_data['position'],
                    sentence=olf_data['sentence'],
                    smell_words=olf_data['smell_words'],  # автоматически в JSON
                    left_context=olf_data['left_context'],
                    right_context=olf_data['right_context']
                )
            print(f"✅ Сохранено {len(olfactory_sentences)} предложений в olfactory_{language}")
        
        # Итог
        total_smell_words = sum(len(olf['smell_words']) for olf in olfactory_sentences)
        
        print(f"\n📊 РЕЗУЛЬТАТ:")
        print(f"   ID текста: {text_id}")
        print(f"   Всего предложений: {len(sentences)}")
        print(f"   Предложений с запахами: {len(olfactory_sentences)}")
        print(f"   Всего слов-запахов: {total_smell_words}")
        
        return {
            'text_id': text_id,
            'language': language,
            'total_sentences': len(sentences),
            'olfactory_sentences': len(olfactory_sentences),
            'olfactory_words': total_smell_words
        }
    
    def process_text(self, text: str,
                    title: str = "Ручной ввод",
                    author: str = "Неизвестен",
                    year: Optional[int] = None,
                    language: Optional[str] = None,
                    is_original: bool = True,
                    original_lang: Optional[str] = None,
                    original_id: Optional[int] = None) -> Dict:
        """
        Обрабатывает текст напрямую (без файла)
        """
        if not language:
            language = self._detect_language(text)
        
        # Сохраняем текст
        if is_original:
            text_id = self.db.texts.add_original(
                language=language,
                title=title,
                author=author,
                year=year,
                content=text
            )
        else:
            text_id = self.db.texts.add_translation(
                language=language,
                title=title,
                author=author,
                year=year,
                content=text,
                original_lang=original_lang,
                original_id=original_id
            )
        
        # Разбиваем на предложения
        sentences = self._split_sentences(text)
        
        # Анализируем
        olfactory_sentences = []
        for pos, sentence in enumerate(sentences, 1):
            result = self._analyze_sentence(sentence, text_id, pos, language)
            if result:
                olfactory_sentences.append(result)
        
        # Сохраняем
        for olf_data in olfactory_sentences:
            self.db.olfactory.add(
                language=language,
                text_id=text_id,
                position=olf_data['position'],
                sentence=olf_data['sentence'],
                smell_words=olf_data['smell_words'],
                left_context=olf_data['left_context'],
                right_context=olf_data['right_context']
            )
        
        return {
            'text_id': text_id,
            'language': language,
            'total_sentences': len(sentences),
            'olfactory_sentences': len(olfactory_sentences)
        }
    
    def reanalyze_text(self, text_id: int, language: str):
        """
        Повторный анализ текста для поиска пропущенных запахов
        (например, после расширения словаря)
        """
        # Получаем полный текст
        text = self.db.texts.get_by_id(language, text_id)
        if not text:
            print("❌ Текст не найден")
            return
        
        print(f"\n🔄 Повторный анализ текста ID {text_id}")
        
        # Получаем уже найденные предложения
        existing = self.db.olfactory.get_by_text(language, text_id)
        existing_positions = {s['position'] for s in existing}
        
        # Разбиваем на предложения
        sentences = self._split_sentences(text['content'])
        
        # Ищем новые
        new_sentences = []
        for pos, sentence in enumerate(sentences, 1):
            if pos not in existing_positions:
                result = self._analyze_sentence(sentence, text_id, pos, language)
                if result:
                    new_sentences.append(result)
        
        # Добавляем новые
        if new_sentences:
            print(f"🔍 Найдено {len(new_sentences)} новых предложений")
            for olf_data in new_sentences:
                self.db.olfactory.add(
                    language=language,
                    text_id=text_id,
                    position=olf_data['position'],
                    sentence=olf_data['sentence'],
                    smell_words=olf_data['smell_words'],
                    left_context=olf_data['left_context'],
                    right_context=olf_data['right_context']
                )
            print(f"✅ Добавлено {len(new_sentences)} предложений")
        else:
            print("✅ Новых предложений не найдено")
        
        return new_sentences