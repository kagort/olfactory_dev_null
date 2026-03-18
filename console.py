#!/usr/bin/env python3
"""
Консольное управление ольфакторной базой данных
Запуск: python console.py
"""

import sys
import json
from pathlib import Path

# Добавляем путь к src
sys.path.append(str(Path(__file__).parent))

from src.database import OlfactoryDB
from src.processors import FileProcessor


class OlfactoryConsole:
    def __init__(self, db_path="data/olfactory.db"):
        self.db = OlfactoryDB(db_path)
        self.db.init()
        self.processor = FileProcessor(self.db)
        self.running = True
        self.supported_languages = ['ru', 'en', 'de']
    
    def clear_screen(self):
        """Очищает экран"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self):
        """Печатает шапку"""
        print("=" * 60)
        print("🌸 ОЛЬФАКТОРНЫЙ АНАЛИЗАТОР 🌸".center(60))
        print("=" * 60)
        print(f"📁 База: {self.db.db.path}")
    
    def print_menu(self):
        """Главное меню"""
        print("\n📌 ГЛАВНОЕ МЕНЮ:")
        print("  [1] 📝 Работа с текстами")
        print("  [2] 📂 Загрузка файлов")
        print("  [3] 🔍 Поиск и анализ ольфакторных предложений")
        print("  [4] 📊 Статистика")
        print("  [5] 🔄 Работа с переводами")
        print("  [6] 🗄️  Прямые SQL запросы")
        print("  [7] 🔗 Выравнивание ольфакторных предложений")
        print("  [8] 📤 Экспорт/импорт CSV для выравнивания")
        print("  [9] 🧹 Ручное добавление пропущенных")
        print("  [0] 🚪 Выход")
    
    # ==================== РАБОТА С ТЕКСТАМИ ====================
    
    def texts_menu(self):
        """Меню работы с текстами"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n📝 ТЕКСТЫ:")
            print("  [1] Показать все тексты")
            print("  [2] Показать тексты по языку")
            print("  [3] Показать текст по ID")
            print("  [4] Добавить текст вручную")
            print("  [5] Удалить текст")
            print("  [6] Показать ольфакторные предложения текста")
            print("  [7] Показать детали ольфакторного предложения")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.show_all_texts()
            elif choice == "2":
                self.show_texts_by_lang()
            elif choice == "3":
                self.show_text_by_id()
            elif choice == "4":
                self.add_text_manual()
            elif choice == "5":
                self.delete_text()
            elif choice == "6":
                self.show_olfactory_sentences()
            elif choice == "7":
                self.show_olfactory_detail()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")
    
    def show_all_texts(self):
        """Показывает все тексты"""
        print("\n📝 ВСЕ ТЕКСТЫ:")
        
        for lang in self.supported_languages:
            texts = self.db.texts.get_by_language(lang)
            if texts:
                lang_symbol = self._get_lang_symbol(lang)
                print(f"\n{lang_symbol} {lang.upper()} ({len(texts)}):")
                for t in texts[:5]:
                    olfactory = self.db.olfactory.get_by_text(lang, t['id'])
                    verified = sum(1 for o in olfactory if o['verified'])
                    total = len(olfactory)
                    print(f"   [{t['id']}] {t['title']} - {t['author']} ({t['year']}) [👃 {total} (✅ {verified})]")
                if len(texts) > 5:
                    print(f"   ... и еще {len(texts) - 5}")
    
    def show_texts_by_lang(self):
        """Показывает тексты по выбранному языку"""
        lang = self._select_language()
        if not lang:
            return
        
        text_type = self._select_text_type()
        
        texts = self.db.texts.get_by_language(lang, text_type)
        lang_name = self._get_lang_name(lang)
        
        print(f"\n📚 {lang_name} тексты ({len(texts)}):")
        for t in texts:
            type_symbol = "🔤" if t['text_type'] == 'original' else "🔄"
            olfactory = self.db.olfactory.get_by_text(lang, t['id'])
            verified = sum(1 for o in olfactory if o['verified'])
            total = len(olfactory)
            print(f"   {type_symbol} [{t['id']}] {t['title']} - {t['author']} ({t['year']}) [👃 {total} (✅ {verified})]")
    
    def show_text_by_id(self):
        """Показывает конкретный текст"""
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста: "))
        except:
            print("❌ Неверный ID")
            return
        
        text = self.db.texts.get_by_id(lang, text_id)
        if not text:
            print(f"❌ Текст {text_id} не найден")
            return
        
        olfactory = self.db.olfactory.get_by_text(lang, text_id)
        verified = sum(1 for o in olfactory if o['verified'])
        
        lang_symbol = self._get_lang_symbol(lang)
        type_symbol = "🔤 ОРИГИНАЛ" if text['text_type'] == 'original' else "🔄 ПЕРЕВОД"
        
        print(f"\n{lang_symbol} {type_symbol}")
        print(f"ID: {text['id']}")
        print(f"Название: {text['title']}")
        print(f"Автор: {text['author']}")
        print(f"Год: {text['year']}")
        print(f"👃 Ольфакторных предложений: {len(olfactory)} (✅ {verified})")
        print("-" * 40)
        print(text['content'][:500] + "..." if len(text['content']) > 500 else text['content'])
        print("-" * 40)
    
    def add_text_manual(self):
        """Добавляет текст вручную"""
        print("\n➕ ДОБАВЛЕНИЕ ТЕКСТА")
        
        title = input("Название: ").strip()
        author = input("Автор: ").strip()
        
        year_str = input("Год (Enter - пропустить): ").strip()
        year = int(year_str) if year_str else None
        
        lang = self._select_language()
        if not lang:
            return
        
        print("\nТип текста:")
        print("  1. Оригинал")
        print("  2. Перевод")
        type_choice = input("👉 Выбор: ").strip()
        
        is_original = (type_choice == "1")
        
        if not is_original:
            print("\nСвязь с оригиналом:")
            orig_lang = self._select_language("Язык оригинала")
            if not orig_lang:
                return
            try:
                orig_id = int(input("ID оригинала: "))
            except:
                print("❌ Неверный ID")
                return
        else:
            orig_lang = None
            orig_id = None
        
        print("\nВведите текст (для завершения введите END в новой строке):")
        lines = []
        while True:
            line = input()
            if line == "END":
                break
            lines.append(line)
        
        text = '\n'.join(lines)
        if not text:
            print("❌ Текст пуст")
            return
        
        result = self.processor.process_text(
            text=text,
            title=title,
            author=author,
            year=year,
            language=lang,
            is_original=is_original,
            original_lang=orig_lang,
            original_id=orig_id
        )
        
        print(f"\n✅ Текст добавлен, ID: {result['text_id']}")
        print(f"👃 Найдено предложений с запахами: {result['olfactory_sentences']}")
    
    def delete_text(self):
        """Удаляет текст"""
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста для удаления: "))
        except:
            print("❌ Неверный ID")
            return
        
        text = self.db.texts.get_by_id(lang, text_id)
        if not text:
            print(f"❌ Текст не найден")
            return
        
        olfactory = self.db.olfactory.get_by_text(lang, text_id)
        
        print(f"\nТекст к удалению: {text['title']} - {text['author']}")
        print(f"👃 Будет удалено {len(olfactory)} ольфакторных предложений")
        
        confirm = input("Удалить? (yes/no): ").lower()
        
        if confirm == 'yes':
            self.db.texts.delete(lang, text_id)
            print("✅ Текст удален")
    
    def show_olfactory_sentences(self):
        """Показывает ольфакторные предложения текста"""
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста: "))
        except:
            print("❌ Неверный ID")
            return
        
        sentences = self.db.olfactory.get_by_text(lang, text_id)
        
        if not sentences:
            print("❌ В этом тексте нет ольфакторных предложений")
            return
        
        text = self.db.texts.get_by_id(lang, text_id)
        
        print(f"\n👃 ОЛЬФАКТОРНЫЕ ПРЕДЛОЖЕНИЯ")
        print(f"📖 {text['title']} - {text['author']}")
        print(f"Всего: {len(sentences)}")
        print("-" * 60)
        
        for s in sentences:
            smell_words = s['smell_words']
            if isinstance(smell_words, str):
                try:
                    smell_words = json.loads(smell_words)
                except:
                    smell_words = []
            
            words_str = ', '.join([w.get('word', str(w)) for w in smell_words[:3]])
            if len(smell_words) > 3:
                words_str += f" и еще {len(smell_words) - 3}"
            
            verified = "✅" if s['verified'] else "⏳"
            aligned = self.db.olfactory.get_aligned_en(s['id'])
            align_status = "🔗" if aligned else "⛓️"
            
            print(f"\n{align_status}{verified} [{s['position']}] {s['sentence'][:200]}...")
            print(f"   👃 Слова: {words_str}")
            print(f"   📝 Контекст: {s['left_context']} → {s['right_context']}")
    
    def show_olfactory_detail(self):
        """Показывает детальную информацию об ольфакторном предложении"""
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста: "))
            sent_pos = int(input("Позиция предложения: "))
        except:
            print("❌ Неверный ввод")
            return
        
        sentences = self.db.olfactory.get_by_text(lang, text_id)
        sentence = None
        for s in sentences:
            if s['position'] == sent_pos:
                sentence = s
                break
        
        if not sentence:
            print("❌ Предложение не найдено")
            return
        
        smell_words = sentence['smell_words']
        if isinstance(smell_words, str):
            try:
                smell_words = json.loads(smell_words)
            except:
                smell_words = []
        
        print(f"\n🔍 ДЕТАЛИ ОЛЬФАКТОРНОГО ПРЕДЛОЖЕНИЯ")
        print("=" * 60)
        print(f"ID: {sentence['id']}")
        print(f"Позиция: {sentence['position']}")
        print(f"Текст: {sentence['sentence']}")
        print(f"\n👃 НАЙДЕННЫЕ СЛОВА-ЗАПАХИ:")
        
        for i, w in enumerate(smell_words, 1):
            if isinstance(w, dict):
                print(f"  {i}. {w.get('word', '?')} (лемма: {w.get('lemma', '?')}, POS: {w.get('pos', '?')})")
            else:
                print(f"  {i}. {w}")
        
        print(f"\n📝 КОНТЕКСТ:")
        print(f"  Слева:  {sentence['left_context']}")
        print(f"  Справа: {sentence['right_context']}")
        print(f"\n✅ Проверено: {'Да' if sentence['verified'] else 'Нет'}")
        
        aligned = self.db.olfactory.get_aligned_en(sentence['id'])
        if aligned:
            print(f"\n🔗 ВЫРОВНЯНО С АНГЛИЙСКИМ:")
            print(f"  Позиция: {aligned['position']}")
            print(f"  Текст: {aligned['sentence'][:200]}...")
    
    # ==================== ЗАГРУЗКА ФАЙЛОВ ====================
    
    def files_menu(self):
        """Меню загрузки файлов"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n📂 ЗАГРУЗКА ФАЙЛОВ:")
            print("  [1] Загрузить оригинал из файла")
            print("  [2] Загрузить перевод из файла")
            print("  [3] Загрузить несколько файлов")
            print("  [4] Загрузить пару (оригинал + перевод)")
            print("  [5] Повторный анализ текста (обновить)")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.load_original_file()
            elif choice == "2":
                self.load_translation_file()
            elif choice == "3":
                self.load_multiple_files()
            elif choice == "4":
                self.load_parallel_files()
            elif choice == "5":
                self.reanalyze_text()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")
    
    def load_original_file(self):
        """Загружает файл как оригинал"""
        print("\n📂 ЗАГРУЗКА ОРИГИНАЛА")
        
        file_path = input("Путь к файлу: ").strip()
        if not file_path:
            return
        
        title = input("Название (Enter - из имени файла): ").strip() or None
        author = input("Автор: ").strip() or None
        
        year_str = input("Год (Enter - пропустить): ").strip()
        year = int(year_str) if year_str else None
        
        lang = self._select_language()
        if not lang:
            return
        
        try:
            result = self.processor.process_file(
                file_path=file_path,
                title=title,
                author=author,
                year=year,
                language=lang,
                is_original=True
            )
            
            print(f"\n✅ Файл загружен!")
            print(f"   ID текста: {result['text_id']}")
            print(f"   Всего предложений: {result['total_sentences']}")
            print(f"   👃 Ольфакторных предложений: {result['olfactory_sentences']}")
            print(f"   🏷️  Всего слов-запахов: {result['olfactory_words']}")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    def load_translation_file(self):
        """Загружает файл как перевод"""
        print("\n📂 ЗАГРУЗКА ПЕРЕВОДА")
        
        print("\nВыберите оригинал:")
        orig_lang = self._select_language("Язык оригинала")
        if not orig_lang:
            return
        
        originals = self.db.texts.get_by_language(orig_lang, 'original')
        if not originals:
            print("❌ Нет оригиналов на этом языке")
            return
        
        print(f"\nОригиналы на {self._get_lang_name(orig_lang)}:")
        for i, t in enumerate(originals[:10], 1):
            olfactory = self.db.olfactory.get_by_text(orig_lang, t['id'])
            print(f"   {i}. [{t['id']}] {t['title']} - {t['author']} [👃 {len(olfactory)}]")
        
        if len(originals) > 10:
            print(f"   ... и еще {len(originals) - 10}")
        
        try:
            orig_id = int(input("ID оригинала: "))
        except:
            print("❌ Неверный ID")
            return
        
        file_path = input("Путь к файлу перевода: ").strip()
        if not file_path:
            return
        
        title = input("Название перевода: ").strip() or None
        translator = input("Переводчик: ").strip() or None
        
        year_str = input("Год перевода (Enter - пропустить): ").strip()
        year = int(year_str) if year_str else None
        
        lang = self._select_language("Язык перевода")
        if not lang:
            return
        
        try:
            result = self.processor.process_file(
                file_path=file_path,
                title=title,
                author=translator,
                year=year,
                language=lang,
                is_original=False,
                original_lang=orig_lang,
                original_id=orig_id
            )
            
            print(f"\n✅ Перевод загружен!")
            print(f"   ID текста: {result['text_id']}")
            print(f"   👃 Ольфакторных предложений: {result['olfactory_sentences']}")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    def load_multiple_files(self):
        """Загружает несколько файлов"""
        print("\n📂 ПАКЕТНАЯ ЗАГРУЗКА")
        print("Введите пути к файлам (по одному в строке, пустая строка - закончить):")
        
        files = []
        while True:
            path = input("  ").strip()
            if not path:
                break
            files.append(path)
        
        if not files:
            return
        
        print(f"\nБудет загружено {len(files)} файлов")
        confirm = input("Продолжить? (y/n): ").lower()
        
        if confirm != 'y':
            return
        
        results = []
        for file_path in files:
            print(f"\n--- {file_path} ---")
            try:
                result = self.processor.process_file(
                    file_path=file_path,
                    is_original=True
                )
                results.append((file_path, True, result))
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                results.append((file_path, False, str(e)))
        
        successful = sum(1 for r in results if r[1])
        total_smells = sum(r[2]['olfactory_sentences'] for r in results if r[1])
        print(f"\n✅ Загружено: {successful} из {len(files)}")
        print(f"👃 Всего ольфакторных предложений: {total_smells}")
    
    def load_parallel_files(self):
        """Загружает пару оригинал + перевод"""
        print("\n📂 ЗАГРУЗКА ПАРЫ ТЕКСТОВ")
        
        orig_file = input("Путь к файлу оригинала: ").strip()
        trans_file = input("Путь к файлу перевода: ").strip()
        
        title = input("Название: ").strip()
        author = input("Автор оригинала: ").strip()
        
        orig_lang = self._select_language("Язык оригинала")
        trans_lang = self._select_language("Язык перевода")
        
        if not orig_lang or not trans_lang:
            return
        
        translator = input("Переводчик: ").strip() or author
        
        print("\n🔄 Загрузка оригиналa...")
        orig_result = self.processor.process_file(
            file_path=orig_file,
            title=title,
            author=author,
            language=orig_lang,
            is_original=True
        )
        
        print("\n🔄 Загрузка перевода...")
        trans_result = self.processor.process_file(
            file_path=trans_file,
            title=title,
            author=translator,
            language=trans_lang,
            is_original=False,
            original_lang=orig_lang,
            original_id=orig_result['text_id']
        )
        
        print(f"\n✅ Готово!")
        print(f"   Оригинал ID: {orig_result['text_id']} (👃 {orig_result['olfactory_sentences']} предложений)")
        print(f"   Перевод ID: {trans_result['text_id']} (👃 {trans_result['olfactory_sentences']} предложений)")
    
    def reanalyze_text(self):
        """Повторный анализ текста (для поиска пропущенных)"""
        print("\n🔄 ПОВТОРНЫЙ АНАЛИЗ ТЕКСТА")
        
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста: "))
        except:
            print("❌ Неверный ID")
            return
        
        result = self.processor.reanalyze_text(text_id, lang)
        
        if result:
            print(f"\n✅ Добавлено {len(result)} новых ольфакторных предложений")
    
    # ==================== ПОИСК И АНАЛИЗ ====================
    
    def search_menu(self):
        """Меню поиска и анализа"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n🔍 ПОИСК И АНАЛИЗ:")
            print("  [1] Найти тексты по автору")
            print("  [2] Найти тексты по году")
            print("  [3] Показать все ольфакторные предложения")
            print("  [4] Показать статистику по тексту")
            print("  [5] Поиск по слову-запаху")
            print("  [6] Показать частотность слов-запахов")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.search_by_author()
            elif choice == "2":
                self.search_by_year()
            elif choice == "3":
                self.show_all_olfactory()
            elif choice == "4":
                self.text_olfactory_stats()
            elif choice == "5":
                self.search_by_smell_word()
            elif choice == "6":
                self.smell_word_frequency()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")
    
    def search_by_author(self):
        """Поиск текстов по автору"""
        author = input("Автор: ").strip()
        if not author:
            return
        
        results = []
        for lang in self.supported_languages:
            texts = self.db.texts.get_by_author(author, lang)
            for t in texts:
                t['language'] = lang
                olfactory = self.db.olfactory.get_by_text(lang, t['id'])
                t['smell_count'] = len(olfactory)
                t['verified'] = sum(1 for o in olfactory if o['verified'])
                results.append(t)
        
        print(f"\n🔎 Найдено текстов: {len(results)}")
        for t in results:
            lang_symbol = self._get_lang_symbol(t['language'])
            type_symbol = "🔤" if t['text_type'] == 'original' else "🔄"
            print(f"   {lang_symbol} {type_symbol} [{t['id']}] {t['title']} ({t['year']}) [👃 {t['smell_count']} (✅ {t['verified']})]")
    
    def search_by_year(self):
        """Поиск текстов по диапазону лет"""
        try:
            start = int(input("Начальный год: "))
            end = int(input("Конечный год: "))
        except:
            print("❌ Неверный год")
            return
        
        results = []
        for lang in self.supported_languages:
            texts = self.db.texts.get_by_year_range(start, end, lang)
            for t in texts:
                t['language'] = lang
                olfactory = self.db.olfactory.get_by_text(lang, t['id'])
                t['smell_count'] = len(olfactory)
                results.append(t)
        
        print(f"\n🔎 Найдено текстов: {len(results)}")
        for t in results:
            lang_symbol = self._get_lang_symbol(t['language'])
            print(f"   {lang_symbol} [{t['id']}] {t['title']} - {t['author']} ({t['year']}) [👃 {t['smell_count']}]")
    
    def show_all_olfactory(self):
        """Показывает все ольфакторные предложения"""
        lang = self._select_language("Язык (Enter - все языки)", required=False)
        
        all_sentences = []
        
        if lang:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                sentences = self.db.olfactory.get_by_text(lang, text['id'])
                for s in sentences:
                    s['title'] = text['title']
                    s['author'] = text['author']
                    s['lang'] = lang
                    all_sentences.append(s)
            print(f"\n👃 Ольфакторные предложения ({lang}):")
        else:
            for l in self.supported_languages:
                texts = self.db.texts.get_by_language(l)
                for text in texts:
                    sentences = self.db.olfactory.get_by_text(l, text['id'])
                    for s in sentences:
                        s['title'] = text['title']
                        s['author'] = text['author']
                        s['lang'] = l
                        all_sentences.append(s)
            print(f"\n👃 Ольфакторные предложения (все языки):")
        
        print(f"Всего: {len(all_sentences)}")
        
        for s in all_sentences[:20]:
            lang_symbol = self._get_lang_symbol(s['lang'])
            verified = "✅" if s['verified'] else "⏳"
            print(f"\n{lang_symbol} {verified} [{s['position']}] {s['sentence'][:200]}...")
            print(f"   📚 {s['title']} - {s['author']}")
        
        if len(all_sentences) > 20:
            print(f"\n... и еще {len(all_sentences) - 20}")
    
    def text_olfactory_stats(self):
        """Показывает статистику по ольфакторным предложениям текста"""
        lang = self._select_language()
        if not lang:
            return
        
        try:
            text_id = int(input("ID текста: "))
        except:
            print("❌ Неверный ID")
            return
        
        text = self.db.texts.get_by_id(lang, text_id)
        if not text:
            print("❌ Текст не найден")
            return
        
        olfactory = self.db.olfactory.get_by_text(lang, text_id)
        
        print(f"\n📊 СТАТИСТИКА ПО ОЛЬФАКТОРНЫМ ПРЕДЛОЖЕНИЯМ")
        print(f"📖 {text['title']} - {text['author']} ({text['year']})")
        print(f"👃 Всего ольфакторных предложений: {len(olfactory)}")
        
        if olfactory:
            verified = sum(1 for s in olfactory if s['verified'])
            print(f"✅ Проверенных: {verified}")
            print(f"⏳ Непроверенных: {len(olfactory) - verified}")
            
            aligned = 0
            total_words = 0
            for s in olfactory:
                if self.db.olfactory.get_aligned_en(s['id']):
                    aligned += 1
                if s['smell_words']:
                    if isinstance(s['smell_words'], str):
                        try:
                            words = json.loads(s['smell_words'])
                            total_words += len(words)
                        except:
                            total_words += 1
                    else:
                        total_words += len(s['smell_words'])
            
            print(f"🔗 Выровнено с переводом: {aligned}")
            print(f"🏷️  Всего слов-запахов: {total_words}")
            print(f"📊 В среднем на предложение: {total_words/len(olfactory):.2f}")
    
    def search_by_smell_word(self):
        """Поиск по конкретному слову-запаху"""
        word = input("Введите слово-запах: ").strip().lower()
        if not word:
            return
        
        lang = self._select_language("Язык (Enter - все языки)", required=False)
        
        results = []
        
        if lang:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                olfactory = self.db.olfactory.get_by_text(lang, text['id'])
                for s in olfactory:
                    smell_words = s['smell_words']
                    if isinstance(smell_words, str):
                        try:
                            smell_words = json.loads(smell_words)
                        except:
                            smell_words = []
                    
                    for w in smell_words:
                        w_text = w.get('word', str(w)) if isinstance(w, dict) else str(w)
                        if word in w_text.lower():
                            s['title'] = text['title']
                            s['author'] = text['author']
                            s['lang'] = lang
                            s['found_word'] = w_text
                            results.append(s)
                            break
        else:
            for l in self.supported_languages:
                texts = self.db.texts.get_by_language(l)
                for text in texts:
                    olfactory = self.db.olfactory.get_by_text(l, text['id'])
                    for s in olfactory:
                        smell_words = s['smell_words']
                        if isinstance(smell_words, str):
                            try:
                                smell_words = json.loads(smell_words)
                            except:
                                smell_words = []
                        
                        for w in smell_words:
                            w_text = w.get('word', str(w)) if isinstance(w, dict) else str(w)
                            if word in w_text.lower():
                                s['title'] = text['title']
                                s['author'] = text['author']
                                s['lang'] = l
                                s['found_word'] = w_text
                                results.append(s)
                                break
        
        print(f"\n🔎 Найдено предложений со словом '{word}': {len(results)}")
        for r in results[:20]:
            lang_symbol = self._get_lang_symbol(r['lang'])
            verified = "✅" if r['verified'] else "⏳"
            print(f"\n{lang_symbol} {verified} [{r['position']}] {r['sentence'][:200]}...")
            print(f"   👃 Найдено: {r['found_word']}")
            print(f"   📚 {r['title']} - {r['author']}")
        
        if len(results) > 20:
            print(f"\n... и еще {len(results) - 20}")
    
    def smell_word_frequency(self):
        """Показывает частотность слов-запахов"""
        lang = self._select_language("Язык (Enter - все языки)", required=False)
        
        from collections import Counter
        
        word_counter = Counter()
        
        if lang:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                olfactory = self.db.olfactory.get_by_text(lang, text['id'])
                for s in olfactory:
                    smell_words = s['smell_words']
                    if isinstance(smell_words, str):
                        try:
                            smell_words = json.loads(smell_words)
                        except:
                            continue
                    
                    for w in smell_words:
                        w_text = w.get('lemma', w.get('word', str(w))) if isinstance(w, dict) else str(w)
                        word_counter[w_text.lower()] += 1
        else:
            for l in self.supported_languages:
                texts = self.db.texts.get_by_language(l)
                for text in texts:
                    olfactory = self.db.olfactory.get_by_text(l, text['id'])
                    for s in olfactory:
                        smell_words = s['smell_words']
                        if isinstance(smell_words, str):
                            try:
                                smell_words = json.loads(smell_words)
                            except:
                                continue
                        
                        for w in smell_words:
                            w_text = w.get('lemma', w.get('word', str(w))) if isinstance(w, dict) else str(w)
                            word_counter[w_text.lower()] += 1
        
        print(f"\n📊 ЧАСТОТНОСТЬ СЛОВ-ЗАПАХОВ:")
        print("-" * 40)
        for word, count in word_counter.most_common(30):
            print(f"   {word:<20} {count:>4}")
    
    # ==================== РАБОТА С ПЕРЕВОДАМИ ====================
    
    def translations_menu(self):
        """Меню работы с переводами"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n🔄 РАБОТА С ПЕРЕВОДАМИ:")
            print("  [1] Показать все переводы текста")
            print("  [2] Найти оригинал по переводу")
            print("  [3] Сравнить ольфакторные предложения")
            print("  [4] Показать выровненные пары")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.show_translations()
            elif choice == "2":
                self.find_original()
            elif choice == "3":
                self.compare_olfactory()
            elif choice == "4":
                self.show_aligned_pairs()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")
    
    def show_translations(self):
        """Показывает все переводы текста"""
        lang = self._select_language("Язык оригинала")
        if not lang:
            return
        
        try:
            text_id = int(input("ID оригинала: "))
        except:
            print("❌ Неверный ID")
            return
        
        translations = self.db.texts.get_translations(lang, text_id)
        
        print(f"\n🔄 Переводы:")
        if not translations:
            print("   Нет переводов")
            return
        
        for t in translations:
            lang_symbol = self._get_lang_symbol(t['language'])
            olfactory = self.db.olfactory.get_by_text(t['language'], t['id'])
            verified = sum(1 for o in olfactory if o['verified'])
            print(f"   {lang_symbol} [{t['id']}] {t['title']} - {t['author']} ({t['year']}) [👃 {len(olfactory)} (✅ {verified})]")
    
    def find_original(self):
        """Находит оригинал по переводу"""
        lang = self._select_language("Язык перевода")
        if not lang:
            return
        
        try:
            text_id = int(input("ID перевода: "))
        except:
            print("❌ Неверный ID")
            return
        
        original = self.db.texts.get_original(lang, text_id)
        
        if original:
            lang_symbol = self._get_lang_symbol(original['language'])
            olfactory = self.db.olfactory.get_by_text(original['language'], original['id'])
            print(f"\n🔤 Оригинал:")
            print(f"   {lang_symbol} [{original['id']}] {original['title']} - {original['author']} ({original['year']}) [👃 {len(olfactory)}]")
        else:
            print("❌ Оригинал не найден")
    
    def compare_olfactory(self):
        """Сравнивает ольфакторные предложения оригинала и перевода"""
        orig_lang = self._select_language("Язык оригинала")
        if not orig_lang:
            return
        
        try:
            orig_id = int(input("ID оригинала: "))
        except:
            print("❌ Неверный ID")
            return
        
        trans_lang = self._select_language("Язык перевода")
        if not trans_lang:
            return
        
        original = self.db.texts.get_by_id(orig_lang, orig_id)
        if not original:
            print("❌ Оригинал не найден")
            return
        
        translations = self.db.texts.get_translations(orig_lang, orig_id)
        translation = None
        for t in translations:
            if t['language'] == trans_lang:
                translation = t
                break
        
        if not translation:
            print(f"❌ Перевод на {trans_lang} не найден")
            return
        
        orig_olfactory = self.db.olfactory.get_by_text(orig_lang, orig_id)
        trans_olfactory = self.db.olfactory.get_by_text(trans_lang, translation['id'])
        
        print(f"\n🔄 СРАВНЕНИЕ ОЛЬФАКТОРНЫХ ПРЕДЛОЖЕНИЙ:")
        print(f"\n🔤 Оригинал ({orig_lang}): {original['title']} - {original['author']}")
        print(f"   👃 Ольфакторных предложений: {len(orig_olfactory)}")
        print(f"\n🔄 Перевод ({trans_lang}): {translation['title']} - {translation['author']}")
        print(f"   👃 Ольфакторных предложений: {len(trans_olfactory)}")
        
        aligned = 0
        for ro in orig_olfactory:
            if self.db.olfactory.get_aligned_en(ro['id']):
                aligned += 1
        
        if aligned > 0:
            print(f"\n🔗 Выровнено пар: {aligned}")
    
    def show_aligned_pairs(self):
        """Показывает выровненные пары русский-английский"""
        print("\n🔗 ВЫРОВНЕННЫЕ ПАРЫ (РУССКИЙ → АНГЛИЙСКИЙ)")
        
        try:
            ru_id = int(input("ID русского текста: "))
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        
        if not ru_olfactory:
            print("❌ В русском тексте нет ольфакторных предложений")
            return
        
        print("\n" + "=" * 100)
        print(f"{'Поз.':<5} {'РУССКОЕ ПРЕДЛОЖЕНИЕ':<45} {'→':<3} {'Поз.':<5} {'АНГЛИЙСКОЕ ПРЕДЛОЖЕНИЕ':<45}")
        print("=" * 100)
        
        found = False
        for ro in ru_olfactory:
            aligned = self.db.olfactory.get_aligned_en(ro['id'])
            if aligned:
                found = True
                
                ru_preview = ro['sentence'][:45] + "..." if len(ro['sentence']) > 45 else ro['sentence']
                en_preview = aligned['sentence'][:45] + "..." if len(aligned['sentence']) > 45 else aligned['sentence']
                
                ru_words = ro['smell_words']
                if isinstance(ru_words, str):
                    try:
                        ru_words = json.loads(ru_words)
                    except:
                        ru_words = []
                
                en_words = aligned['smell_words']
                if isinstance(en_words, str):
                    try:
                        en_words = json.loads(en_words)
                    except:
                        en_words = []
                
                ru_words_str = ', '.join([w.get('word', str(w)) for w in ru_words[:3]])
                en_words_str = ', '.join([w.get('word', str(w)) for w in en_words[:3]])
                
                verified = "✅" if aligned['verified'] else "⏳"
                
                print(f"{ro['position']:<5} {ru_preview:<45} {'→':<3} {aligned['position']:<5} {en_preview:<45}")
                print(f"      👃 {ru_words_str:<42} 👃 {en_words_str:<42} {verified}")
                print(f"      📝 {ro['left_context']} → {ro['right_context']}")
                print(f"      📝 {aligned['left_context']} → {aligned['right_context']}")
        
        if not found:
            print("❌ Нет выровненных пар")
    
    # ==================== СТАТИСТИКА ====================
    
    def stats_menu(self):
        """Меню статистики"""
        self.clear_screen()
        self.print_header()
        
        print("\n📊 ОБЩАЯ СТАТИСТИКА:")
        print("=" * 40)
        
        total_texts = 0
        total_olfactory = 0
        total_verified = 0
        total_aligned = 0
        
        for lang in self.supported_languages:
            texts = self.db.texts.get_by_language(lang)
            lang_texts = len(texts)
            total_texts += lang_texts
            
            lang_olfactory = 0
            lang_verified = 0
            lang_aligned = 0
            
            for t in texts:
                olfactory = self.db.olfactory.get_by_text(lang, t['id'])
                lang_olfactory += len(olfactory)
                lang_verified += sum(1 for o in olfactory if o['verified'])
                for o in olfactory:
                    if lang == 'ru' and self.db.olfactory.get_aligned_en(o['id']):
                        lang_aligned += 1
            
            total_olfactory += lang_olfactory
            total_verified += lang_verified
            total_aligned += lang_aligned
            
            lang_symbol = self._get_lang_symbol(lang)
            print(f"\n{lang_symbol} {lang.upper()}:")
            print(f"   Текстов: {lang_texts}")
            print(f"   👃 Ольфакторных предложений: {lang_olfactory}")
            print(f"   ✅ Проверенных: {lang_verified}")
            if lang == 'ru':
                print(f"   🔗 Выровненных с переводом: {lang_aligned}")
        
        print("\n" + "=" * 40)
        print(f"📈 ВСЕГО:")
        print(f"   Текстов: {total_texts}")
        print(f"   👃 Ольфакторных предложений: {total_olfactory}")
        print(f"   ✅ Проверенных: {total_verified}")
        print(f"   🔗 Выровненных пар: {total_aligned}")
        
        input("\n⏎ Нажми Enter для продолжения...")
    
    # ==================== SQL МЕНЮ ====================
    
    def sql_menu(self):
        """Прямые SQL запросы"""
        self.clear_screen()
        self.print_header()
        print("\n🗄️  ПРЯМЫЕ SQL ЗАПРОСЫ")
        print("Вводите SQL запросы (пустая строка - выход)")
        print("\nДоступные таблицы:")
        for lang in self.supported_languages:
            print(f"  - texts_{lang}")
            print(f"  - olfactory_{lang}")
        print("  - text_relations")
        print("  - olfactory_alignments")
        print("\nПримеры полезных запросов:")
        print("  -- Показать все выровненные пары")
        print("  SELECT ru.id, ru.sentence, en.sentence FROM olfactory_alignments a")
        print("  JOIN olfactory_ru ru ON a.ru_id = ru.id")
        print("  JOIN olfactory_en en ON a.en_id = en.id;")
        print("\n  -- Показать невыровненные русские предложения")
        print("  SELECT * FROM olfactory_ru WHERE id NOT IN (SELECT ru_id FROM olfactory_alignments);")
        print("-" * 40)
        
        while True:
            print("\nSQL> ", end="")
            sql = input().strip()
            
            if not sql:
                break
            
            try:
                results = self.db.db.execute(sql)
                
                if isinstance(results, list):
                    print(f"\n📊 Результатов: {len(results)}")
                    for row in results[:10]:
                        print(row)
                    if len(results) > 10:
                        print(f"... и еще {len(results) - 10}")
                else:
                    print(f"✅ Выполнено, изменено строк: {results}")
                    
            except Exception as e:
                print(f"❌ Ошибка: {e}")
    
    # ==================== ВЫРАВНИВАНИЕ ====================
    
    def alignment_menu(self):
        """Меню выравнивания ольфакторных предложений"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n🔗 ВЫРАВНИВАНИЕ ОЛЬФАКТОРНЫХ ПРЕДЛОЖЕНИЙ:")
            print("  [1] Показать пары текстов")
            print("  [2] Выровнять предложения вручную")
            print("  [3] Показать выровненные пары")
            print("  [4] Проверить/исправить выравнивание")
            print("  [5] Показать невыровненные")
            print("  [6] Статистика выравнивания")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.show_alignable_pairs()
            elif choice == "2":
                self.manual_olfactory_alignment()
            elif choice == "3":
                self.show_aligned_pairs()
            elif choice == "4":
                self.verify_olfactory_alignment()
            elif choice == "5":
                self.show_unaligned()
            elif choice == "6":
                self.alignment_statistics()
            elif choice == "0":
                break
            else:
                print("❌ Неверный выбор")
            
            if choice != "0":
                input("\n⏎ Нажми Enter для продолжения...")
    
    def show_alignable_pairs(self):
        """Показывает пары текстов с ольфакторными предложениями"""
        print("\n📚 ПАРЫ ДЛЯ ВЫРАВНИВАНИЯ:")
        
        ru_texts = self.db.texts.get_by_language('ru', 'original')
        
        if not ru_texts:
            print("❌ Нет русских оригиналов")
            return
        
        found = False
        for ru_text in ru_texts:
            translations = self.db.texts.get_translations('ru', ru_text['id'])
            
            if translations:
                ru_olfactory = self.db.olfactory.get_by_text('ru', ru_text['id'])
                if not ru_olfactory:
                    continue
                
                found = True
                ru_verified = sum(1 for o in ru_olfactory if o['verified'])
                print(f"\n🇷🇺 [{ru_text['id']}] {ru_text['title']} - {ru_text['author']}")
                print(f"   👃 Ольфакторных предложений: {len(ru_olfactory)} (✅ {ru_verified})")
                
                for en_text in translations:
                    en_olfactory = self.db.olfactory.get_by_text('en', en_text['id'])
                    
                    aligned_count = 0
                    for ro in ru_olfactory:
                        if self.db.olfactory.get_aligned_en(ro['id']):
                            aligned_count += 1
                    
                    en_verified = sum(1 for o in en_olfactory if o['verified'])
                    status = f"✅ {aligned_count}/{len(ru_olfactory)} выровнено" if aligned_count > 0 else "❌ не выровнено"
                    print(f"   🇬🇧 [{en_text['id']}] {en_text['title']} - {status} (👃 {len(en_olfactory)}, ✅ {en_verified})")
        
        if not found:
            print("❌ Нет пар с ольфакторными предложениями")
    
    def manual_olfactory_alignment(self):
        """Ручное выравнивание ольфакторных предложений"""
        print("\n🔄 РУЧНОЕ ВЫРАВНИВАНИЕ")
        
        try:
            ru_id = int(input("ID русского текста: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_text = self.db.texts.get_by_id('ru', ru_id)
        if not ru_text:
            print("❌ Русский текст не найден")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        if not ru_olfactory:
            print("❌ В этом тексте нет ольфакторных предложений")
            return
        
        translations = self.db.texts.get_translations('ru', ru_id)
        if not translations:
            print("❌ Нет переводов для этого текста")
            return
        
        print("\nДоступные переводы:")
        for t in translations:
            en_olfactory = self.db.olfactory.get_by_text('en', t['id'])
            print(f"  [{t['id']}] {t['title']} (👃 {len(en_olfactory)})")
        
        try:
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        if not en_olfactory:
            print("❌ В английском переводе нет ольфакторных предложений")
            return
        
        unaligned_ru = []
        for ro in ru_olfactory:
            if not self.db.olfactory.get_aligned_en(ro['id']):
                unaligned_ru.append(ro)
        
        if not unaligned_ru:
            print("✅ Все ольфакторные предложения уже выровнены!")
            return
        
        print(f"\n📝 НЕВЫРОВНЕННЫЕ РУССКИЕ ПРЕДЛОЖЕНИЯ:")
        for i, ro in enumerate(unaligned_ru, 1):
            smell_words = ro['smell_words']
            if isinstance(smell_words, str):
                try:
                    smell_words = json.loads(smell_words)
                except:
                    smell_words = []
            words_str = ', '.join([w.get('word', str(w)) for w in smell_words[:3]])
            print(f"\n  {i}. [{ro['position']}] {ro['sentence'][:150]}...")
            print(f"      👃 {words_str}")
        
        print(f"\n📝 АНГЛИЙСКИЕ ПРЕДЛОЖЕНИЯ ДЛЯ ВЫРАВНИВАНИЯ:")
        en_by_pos = {}
        for eo in en_olfactory:
            en_by_pos[eo['position']] = eo
            smell_words = eo['smell_words']
            if isinstance(smell_words, str):
                try:
                    smell_words = json.loads(smell_words)
                except:
                    smell_words = []
            words_str = ', '.join([w.get('word', str(w)) for w in smell_words[:3]])
            print(f"\n  [{eo['position']}] {eo['sentence'][:150]}...")
            print(f"      👃 {words_str}")
        
        print("\n--- ВЫРАВНИВАНИЕ ---")
        print("Вводите пары: русская_позиция английская_позиция")
        print("Пустая строка - выход")
        
        while True:
            try:
                pair = input("\nПара (ru_pos en_pos): ").strip()
                if not pair:
                    break
                
                ru_pos, en_pos = map(int, pair.split())
                
                ru_sent = None
                for ro in ru_olfactory:
                    if ro['position'] == ru_pos:
                        ru_sent = ro
                        break
                
                en_sent = en_by_pos.get(en_pos)
                
                if not ru_sent or not en_sent:
                    print("❌ Неверные позиции")
                    continue
                
                existing = self.db.olfactory.get_aligned_en(ru_sent['id'])
                if existing:
                    print(f"⚠️ Русское предложение уже выровнено с английским [{existing['position']}]")
                    overwrite = input("Перезаписать? (y/n): ").lower()
                    if overwrite != 'y':
                        continue
                
                self.db.olfactory.align(ru_sent['id'], en_sent['id'])
                print(f"✅ Выровнено: русское [{ru_pos}] → английское [{en_pos}]")
                
            except ValueError:
                print("❌ Введите два числа")
            except KeyboardInterrupt:
                break
    
    def verify_olfactory_alignment(self):
        """Проверить и исправить выравнивание"""
        print("\n🔍 ПРОВЕРКА ВЫРАВНИВАНИЯ")
        
        try:
            ru_id = int(input("ID русского текста: "))
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        en_by_pos = {eo['position']: eo for eo in en_olfactory}
        
        checked = 0
        for ro in ru_olfactory:
            aligned = self.db.olfactory.get_aligned_en(ro['id'])
            if aligned:
                checked += 1
                print(f"\n--- ПАРА {ro['position']} → {aligned['position']} ---")
                print(f"🇷🇺: {ro['sentence'][:200]}...")
                print(f"🇬🇧: {aligned['sentence'][:200]}...")
                
                ru_words = ro['smell_words']
                if isinstance(ru_words, str):
                    try:
                        ru_words = json.loads(ru_words)
                    except:
                        ru_words = []
                
                en_words = aligned['smell_words']
                if isinstance(en_words, str):
                    try:
                        en_words = json.loads(en_words)
                    except:
                        en_words = []
                
                print(f"   👃 Русские слова: {', '.join([w.get('word', str(w)) for w in ru_words])}")
                print(f"   👃 Английские слова: {', '.join([w.get('word', str(w)) for w in en_words])}")
                
                cmd = input("Верно? (y/n/q): ").lower()
                if cmd == 'n':
                    print("\nДоступные английские предложения:")
                    for pos, eo in list(en_by_pos.items())[:10]:
                        preview = eo['sentence'][:100] + "..." if len(eo['sentence']) > 100 else eo['sentence']
                        print(f"  [{pos}] {preview}")
                    
                    try:
                        new_pos = int(input("Правильная позиция английского: "))
                        new_en = en_by_pos.get(new_pos)
                        
                        if new_en:
                            self.db.olfactory.align(ro['id'], new_en['id'])
                            print("✅ Исправлено")
                        else:
                            print("❌ Неверная позиция")
                    except ValueError:
                        print("❌ Ошибка")
                elif cmd == 'q':
                    break
        
        if checked == 0:
            print("❌ Нет выровненных пар")
    
    def show_unaligned(self):
        """Показать невыровненные ольфакторные предложения"""
        print("\n❌ НЕВЫРОВНЕННЫЕ ПРЕДЛОЖЕНИЯ")
        
        try:
            ru_id = int(input("ID русского текста: "))
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        
        unaligned_ru = []
        for ro in ru_olfactory:
            if not self.db.olfactory.get_aligned_en(ro['id']):
                unaligned_ru.append(ro)
        
        unaligned_en = []
        for eo in en_olfactory:
            if not self.db.olfactory.get_aligned_ru(eo['id']):
                unaligned_en.append(eo)
        
        print(f"\n🇷🇺 Невыровненных русских: {len(unaligned_ru)}")
        for ro in unaligned_ru[:10]:
            print(f"  [{ro['position']}] {ro['sentence'][:100]}...")
        
        if len(unaligned_ru) > 10:
            print(f"  ... и еще {len(unaligned_ru) - 10}")
        
        print(f"\n🇬🇧 Невыровненных английских: {len(unaligned_en)}")
        for eo in unaligned_en[:10]:
            print(f"  [{eo['position']}] {eo['sentence'][:100]}...")
        
        if len(unaligned_en) > 10:
            print(f"  ... и еще {len(unaligned_en) - 10}")
    
    def alignment_statistics(self):
        """Статистика по выравниванию"""
        print("\n📊 СТАТИСТИКА ВЫРАВНИВАНИЯ")
        
        try:
            ru_id = int(input("ID русского текста: "))
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        
        total_ru = len(ru_olfactory)
        total_en = len(en_olfactory)
        
        aligned_ru = 0
        aligned_en = 0
        word_match = 0
        
        for ro in ru_olfactory:
            aligned = self.db.olfactory.get_aligned_en(ro['id'])
            if aligned:
                aligned_ru += 1
                
                ru_words = ro['smell_words']
                if isinstance(ru_words, str):
                    try:
                        ru_words = json.loads(ru_words)
                    except:
                        ru_words = []
                
                en_words = aligned['smell_words']
                if isinstance(en_words, str):
                    try:
                        en_words = json.loads(en_words)
                    except:
                        en_words = []
                
                if len(ru_words) == len(en_words):
                    word_match += 1
        
        for eo in en_olfactory:
            if self.db.olfactory.get_aligned_ru(eo['id']):
                aligned_en += 1
        
        print(f"\n📊 СТАТИСТИКА:")
        print(f"   Русских предложений: {total_ru}")
        print(f"   Английских предложений: {total_en}")
        if total_ru > 0:
            print(f"   Выровнено русских: {aligned_ru} ({aligned_ru/total_ru*100:.1f}%)")
        if total_en > 0:
            print(f"   Выровнено английских: {aligned_en} ({aligned_en/total_en*100:.1f}%)")
        if aligned_ru > 0:
            print(f"   Совпадение по количеству слов: {word_match}/{aligned_ru} ({word_match/aligned_ru*100:.1f}%)")
    
    # ==================== ЭКСПОРТ/ИМПОРТ CSV ====================
    
    def csv_menu(self):
        """Меню экспорта/импорта CSV"""
        while True:
            self.clear_screen()
            self.print_header()
            print("\n📤 ЭКСПОРТ/ИМПОРТ CSV:")
            print("  [1] Экспорт для выравнивания")
            print("  [2] Импорт выравниваний из CSV")
            print("  [3] Экспорт всех ольфакторных данных (один язык)")
            print("  [4] Экспорт статистики")
            print("  [5] 🔗 Экспорт выровненных предложений (русский + английский)")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.export_alignment_csv()
            elif choice == "2":
                self.import_alignment_csv()
            elif choice == "3":
                self.export_all_olfactory()
            elif choice == "4":
                self.export_statistics_csv()
            elif choice == "5":
                self.export_detailed_alignment()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")
    
    def export_alignment_csv(self):
        """Экспорт ольфакторных предложений для выравнивания в CSV"""
        try:
            import pandas as pd
        except ImportError:
            print("❌ Установите pandas: pip install pandas")
            return
        
        from pathlib import Path
        
        print("\n📤 ЭКСПОРТ ДЛЯ ВЫРАВНИВАНИЯ")
        
        try:
            ru_id = int(input("ID русского текста: "))
            en_id = int(input("ID английского перевода: "))
        except ValueError:
            print("❌ Неверный ID")
            return
        
        ru_text = self.db.texts.get_by_id('ru', ru_id)
        en_text = self.db.texts.get_by_id('en', en_id)
        
        if not ru_text or not en_text:
            print("❌ Текст не найден")
            return
        
        ru_olfactory = self.db.olfactory.get_by_text('ru', ru_id)
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        
        if not ru_olfactory:
            print("❌ В русском тексте нет ольфакторных предложений")
            return
        
        print(f"\n🇷🇺 Русских ольфакторных предложений: {len(ru_olfactory)}")
        print(f"🇬🇧 Английских ольфакторных предложений: {len(en_olfactory)}")
        
        data = []
        
        for ro in ru_olfactory:
            ru_words = ro['smell_words']
            if isinstance(ru_words, str):
                try:
                    ru_words = json.loads(ru_words)
                except:
                    ru_words = []
            
            ru_words_str = ', '.join([w.get('word', str(w)) for w in ru_words[:5]])
            if len(ru_words) > 5:
                ru_words_str += f" и еще {len(ru_words) - 5}"
            
            aligned = self.db.olfactory.get_aligned_en(ro['id'])
            current = aligned['position'] if aligned else ''
            
            row = {
                'ru_id': ro['id'],
                'ru_pos': ro['position'],
                'ru_sentence': ro['sentence'][:200] + "..." if len(ro['sentence']) > 200 else ro['sentence'],
                'ru_smell_words': ru_words_str,
                'ru_context': f"{ro['left_context']} → {ro['right_context']}",
                'current_alignment': current,
                'new_alignment': ''
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        
        output = Path(f"alignment_ru{ru_id}_en{en_id}.csv")
        df.to_csv(output, index=False, encoding='utf-8-sig')
        
        print(f"\n✅ Экспортировано {len(ru_olfactory)} русских предложений в {output}")
        print("\n📌 АНГЛИЙСКИЕ ПРЕДЛОЖЕНИЯ ДЛЯ ВЫРАВНИВАНИЯ:")
        print("=" * 80)
        for eo in en_olfactory:
            en_words = eo['smell_words']
            if isinstance(en_words, str):
                try:
                    en_words = json.loads(en_words)
                except:
                    en_words = []
            
            en_words_str = ', '.join([w.get('word', str(w)) for w in en_words[:3]])
            if len(en_words) > 3:
                en_words_str += f" (+{len(en_words)-3})"
            
            print(f"\n📌 ПОЗИЦИЯ {eo['position']}:")
            print(f"   Текст: {eo['sentence']}")
            print(f"   Слова-запахи: {en_words_str}")
            print(f"   Контекст: {eo['left_context']} → {eo['right_context']}")
            print("-" * 60)
        
        print("\n📌 КАК ЗАПОЛНЯТЬ:")
        print("   В колонке 'new_alignment' укажите ПОЗИЦИЮ английского предложения,")
        print("   которое соответствует русскому. Например: 3")
        print("   Если соответствия нет - оставьте пустым")
        print("\n   Английские предложения с их позициями см. выше ↑")
    
    def import_alignment_csv(self):
        """Импорт выравниваний из CSV"""
        try:
            import pandas as pd
        except ImportError:
            print("❌ Установите pandas: pip install pandas")
            return
        
        print("\n📥 ИМПОРТ ВЫРАВНИВАНИЙ ИЗ CSV")
        
        file_path = input("Путь к CSV файлу: ").strip()
        
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            print(f"❌ Ошибка чтения файла: {e}")
            return
        
        required = ['ru_id', 'new_alignment']
        missing = [col for col in required if col not in df.columns]
        if missing:
            print(f"❌ В CSV отсутствуют колонки: {missing}")
            return
        
        first_row = df.iloc[0]
        ru_id = int(first_row['ru_id'])
        
        ru_text = self.db.texts.get_by_id('ru', ru_id)
        if not ru_text:
            print("❌ Русский текст не найден")
            return
        
        translations = self.db.texts.get_translations('ru', ru_id)
        if not translations:
            print("❌ Нет переводов для этого текста")
            return
        
        if len(translations) == 1:
            en_id = translations[0]['id']
        else:
            print("\nДоступные переводы:")
            for t in translations:
                print(f"  [{t['id']}] {t['title']}")
            try:
                en_id = int(input("ID английского перевода: "))
            except:
                print("❌ Неверный ID")
                return
        
        en_olfactory = self.db.olfactory.get_by_text('en', en_id)
        en_by_pos = {eo['position']: eo for eo in en_olfactory}
        
        success = 0
        errors = []
        
        for _, row in df.iterrows():
            if pd.notna(row['new_alignment']) and str(row['new_alignment']).strip():
                try:
                    ru_id = int(row['ru_id'])
                    en_pos = int(str(row['new_alignment']).strip())
                    
                    ru_sent = self.db.olfactory.get_by_id('ru', ru_id)
                    if not ru_sent:
                        errors.append(f"Русское предложение {ru_id} не найдено")
                        continue
                    
                    en_sent = en_by_pos.get(en_pos)
                    if not en_sent:
                        errors.append(f"Английское предложение на позиции {en_pos} не найдено")
                        continue
                    
                    self.db.olfactory.align(ru_id, en_sent['id'])
                    success += 1
                    
                except (ValueError, TypeError) as e:
                    errors.append(f"Ошибка в строке: {e}")
        
        print(f"\n✅ Успешно импортировано: {success} выравниваний")
        if errors:
            print(f"\n⚠️ Ошибки ({len(errors)}):")
            for e in errors[:5]:
                print(f"   {e}")
            if len(errors) > 5:
                print(f"   ... и еще {len(errors) - 5}")
    
    def export_all_olfactory(self):
        """Экспорт всех ольфакторных данных в CSV"""
        try:
            import pandas as pd
        except ImportError:
            print("❌ Установите pandas: pip install pandas")
            return
        
        from pathlib import Path
        
        print("\n📤 ЭКСПОРТ ВСЕХ ОЛЬФАКТОРНЫХ ДАННЫХ")
        
        lang = self._select_language()
        if not lang:
            return
        
        data = []
        
        texts = self.db.texts.get_by_language(lang)
        for text in texts:
            olfactory = self.db.olfactory.get_by_text(lang, text['id'])
            for o in olfactory:
                smell_words = o['smell_words']
                if isinstance(smell_words, str):
                    try:
                        smell_words = json.loads(smell_words)
                    except:
                        smell_words = []
                
                words_str = '; '.join([f"{w.get('word', str(w))}({w.get('pos', '?')})" for w in smell_words])
                
                aligned = self.db.olfactory.get_aligned_en(o['id']) if lang == 'ru' else None
                
                row = {
                    'text_id': text['id'],
                    'title': text['title'],
                    'author': text['author'],
                    'year': text['year'],
                    'text_type': text['text_type'],
                    'sent_position': o['position'],
                    'sentence': o['sentence'],
                    'smell_words': words_str,
                    'left_context': o['left_context'],
                    'right_context': o['right_context'],
                    'verified': o['verified'],
                    'aligned_to': aligned['position'] if aligned else ''
                }
                data.append(row)
        
        df = pd.DataFrame(data)
        output = Path(f"olfactory_data_{lang}.csv")
        df.to_csv(output, index=False, encoding='utf-8-sig')
        print(f"✅ Экспортировано {len(data)} записей в {output}")
    
    def export_statistics_csv(self):
        """Экспорт статистики в CSV"""
        try:
            import pandas as pd
        except ImportError:
            print("❌ Установите pandas: pip install pandas")
            return
        
        from pathlib import Path
        
        print("\n📤 ЭКСПОРТ СТАТИСТИКИ")
        
        data = []
        
        for lang in self.supported_languages:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                olfactory = self.db.olfactory.get_by_text(lang, text['id'])
                
                row = {
                    'language': lang,
                    'text_id': text['id'],
                    'title': text['title'],
                    'author': text['author'],
                    'year': text['year'],
                    'text_type': text['text_type'],
                    'olfactory_count': len(olfactory),
                    'verified_count': sum(1 for o in olfactory if o['verified'])
                }
                data.append(row)
        
        df = pd.DataFrame(data)
        output = Path("statistics.csv")
        df.to_csv(output, index=False, encoding='utf-8-sig')
        print(f"✅ Экспортировано {len(data)} записей в {output}")
    
    def export_detailed_alignment(self):
        """Экспорт детального выравнивания (все языки)"""
        print("\n🔗 ЭКСПОРТ ДЕТАЛЬНОГО ВЫРАВНИВАНИЯ")
        print("=" * 60)
        
        # 1. Выбираем режим экспорта
        print("\n📋 РЕЖИМ ЭКСПОРТА:")
        print("  1. Экспортировать ВСЕ тексты (все языки)")
        print("  2. Экспортировать тексты по автору")
        
        mode = input("\n👉 Выбор (1 или 2): ").strip()
        
        texts_to_export = []
        
        if mode == "1":
            # Экспортируем все тексты на всех языках
            print("\n🌐 ЗАГРУЗКА ВСЕХ ТЕКСТОВ...")
            for lang in self.supported_languages:
                texts = self.db.texts.get_by_language(lang)
                for text in texts:
                    text['language'] = lang
                    texts_to_export.append(text)
            print(f"✅ Найдено текстов: {len(texts_to_export)}")
        
        elif mode == "2":
            # Экспортируем по автору
            author = input("\n📝 Введите имя автора: ").strip()
            if not author:
                print("❌ Автор не указан")
                return
            
            print(f"\n🔍 ПОИСК ТЕКСТОВ АВТОРА: {author}")
            
            # Ищем во всех языках
            for lang in self.supported_languages:
                texts = self.db.texts.get_by_author(author, lang)
                for text in texts:
                    text['language'] = lang
                    texts_to_export.append(text)
            
            if not texts_to_export:
                print(f"❌ Тексты автора '{author}' не найдены")
                return
            
            print(f"✅ Найдено текстов: {len(texts_to_export)}")
            
            # Показываем найденные тексты
            print("\n📚 НАЙДЕННЫЕ ТЕКСТЫ:")
            for t in texts_to_export:
                lang_symbol = self._get_lang_symbol(t['language'])
                olfactory = self.db.olfactory.get_by_text(t['language'], t['id'])
                print(f"   {lang_symbol} [ID: {t['id']:3d}] {t['title']} - {t['author']} (👃 {len(olfactory)})")
        
        else:
            print("❌ Неверный выбор")
            return
        
        # 2. Спрашиваем путь для сохранения
        print("\n📁 СОХРАНЕНИЕ:")
        
        if mode == "1":
            default_name = f"data/alignment_all_texts.csv"
        else:
            author_clean = author.replace(' ', '_')[:30]
            default_name = f"data/alignment_{author_clean}.csv"
        
        output = input(f"Путь для сохранения (Enter - {default_name}): ").strip()
        if not output:
            output = default_name
        
        # 3. Подтверждение
        print(f"\n📊 Будет обработано текстов: {len(texts_to_export)}")
        print(f"📁 Файл: {output}")
        confirm = input("\nПродолжить? (y/n): ").lower()
        
        if confirm != 'y':
            print("❌ Отменено")
            return
        
        # 4. Экспортируем
        try:
            print("\n🔄 Экспорт данных...")
            import pandas as pd
            import json
            from pathlib import Path
            
            all_rows = []
            
            for text in texts_to_export:
                lang = text['language']
                text_id = text['id']
                
                # Получаем ольфакторные предложения для этого текста
                sentences = self.db.olfactory.get_by_text(lang, text_id)
                
                for sent in sentences:
                    # Парсим слова-запахи
                    smell_words = sent.get('smell_words', [])
                    if isinstance(smell_words, str):
                        try:
                            smell_words = json.loads(smell_words)
                        except:
                            smell_words = []
                    
                    # Если нет слов-запахов, создаем одну строку с пустым токеном
                    if not smell_words:
                        smell_words = [{}]
                    
                    # Создаем строку для каждого токена
                    for i, word in enumerate(smell_words):
                        # Определяем, какой язык заполнять
                        row = {
                            # Основная информация
                            'txt_ID': text_id,
                            'language': lang,
                            'author': text['author'],
                            'title': text['title'],
                            'year': text['year'],
                            'sent_ID': sent['id'],
                            'sent_position': sent['position'],
                            
                            # Общие поля для всех языков
                            'sent_text': sent['sentence'] if i == 0 else '',
                            'token_ID': i + 1,
                            'token': word.get('word', ''),
                            'token_pos': word.get('pos', ''),
                            'concept_unit': word.get('concept', word.get('word', '')),
                            'type': sent.get('type', ''),
                            'connotation': sent.get('connotation', ''),
                            'intensity': '',
                            'tonality': sent.get('tonal', ''),
                            'gram_structure': sent.get('gramm_structure', ''),
                            'comments': sent.get('comments', ''),
                            
                            # Поля для выравнивания (заполняются, если есть перевод)
                            'aligned_text_ID': '',
                            'aligned_language': '',
                            'aligned_sent_text': '',
                            'aligned_token': '',
                            'aligned_token_pos': '',
                            'aligned_concept': '',
                            
                            # Метаданные
                            'verified': sent.get('verified', 0)
                        }
                        
                        # Если есть выравнивание с другим языком
                        if lang == 'ru':
                            aligned = self.db.olfactory.get_aligned_en(sent['id'])
                            if aligned:
                                row.update({
                                    'aligned_text_ID': aligned['text_id'],
                                    'aligned_language': 'en',
                                    'aligned_sent_text': aligned['sentence'] if i == 0 else '',
                                    'aligned_token': word.get('word', '') if i < len(aligned.get('smell_words', [])) else '',
                                    'aligned_token_pos': word.get('pos', '') if i < len(aligned.get('smell_words', [])) else '',
                                    'aligned_concept': word.get('concept', word.get('word', '')) if i < len(aligned.get('smell_words', [])) else '',
                                })
                        
                        all_rows.append(row)
                
                print(f" ✅ {len(sentences)} предложений")
            
            # Создаем DataFrame
            df = pd.DataFrame(all_rows)
            
            # Сохраняем
            df.to_csv(output, index=False, encoding='utf-8-sig')
            
            print(f"\n✅ CSV успешно создан!")
            print(f"📁 Файл: {output}")
            print(f"\n📊 Статистика:")
            print(f"   Всего текстов: {len(texts_to_export)}")
            print(f"   Всего строк: {len(df)}")
            print(f"   Всего колонок: {len(df.columns)}")
            
            # Показываем preview
            print(f"\n📋 Первые 5 строк:")
            preview_cols = ['language', 'author', 'title', 'sent_position', 'token', 'aligned_language']
            print(df[preview_cols].head(5).to_string())
            
        except Exception as e:
            print(f"\n❌ Ошибка при экспорте: {e}")
            import traceback
            traceback.print_exc()
        
    # ==================== ЗАПУСК ====================
        
    def run(self):
        """Запуск консоли"""
        while self.running:
            self.clear_screen()
            self.print_header()
            self.print_menu()
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.texts_menu()
            elif choice == "2":
                self.files_menu()
            elif choice == "3":
                self.search_menu()
            elif choice == "4":
                self.stats_menu()
            elif choice == "5":
                self.translations_menu()
            elif choice == "6":
                self.sql_menu()
            elif choice == "7":
                self.alignment_menu()
            elif choice == "8":
                self.csv_menu()
            elif choice == "9":
                self.manual_add_menu()
            elif choice == "0":
                print("\n👋 До свидания!")
                self.running = False
            else:
                print("❌ Неверный выбор")
                input("⏎ Нажми Enter...")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/olfactory.db"
    
    console = OlfactoryConsole(db_path)
    try:
        console.run()
    except KeyboardInterrupt:
        print("\n\n👋 До свидания!")