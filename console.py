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
        
    def _select_language(self, prompt="Язык (ru/en/de): "):
        """Выбор языка. Повторяет ввод при ошибке"""
        while True:
            lang = input(prompt).strip().lower()
            if lang in self.supported_languages:
                return lang
            print(f"❌ Ошибка! Поддерживаются: {', '.join(self.supported_languages)}")
            
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
        print("  [1] 📂 Загрузка файлов")
        print("  [2] 🔗 Выравнивание ольфакторных предложений")
        # print("  [3] 📊 Статистика")
        print("  [0] 🚪 Выход")


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
                self.load_file('original')
            elif choice == "2":
                self.load_file('translation')
            elif choice == "3":
                self.load_multiple_files()
            elif choice == "4":
                self.load_parallel_files()
            elif choice == "5":
                self.reanalyze_text()
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")

    def _ask_metadata(self, ask_translator=False, ask_language=True):
        """Запрашивает метаданные"""
        title = input("Название (Enter - из имени файла): ").strip() or None
        author = input("Автор: ").strip() or None
        
        translator = input("Переводчик: ").strip() or None if ask_translator else None
        
        year_str = input("Год (Enter - пропустить): ").strip()
        year = int(year_str) if year_str else None
        
        return title, author, translator, year

    def load_file(self, file_type='original'):
        orig_lang = None
        orig_id = None
        translator = None
        
        if file_type == 'translation':
            print("\nВыберите оригинал:")
            orig_lang = self._select_language("Язык оригинала")
            
            originals = self.db.texts.find(orig_lang, text_type='original')
            if not originals:
                print("❌ Нет оригиналов на этом языке")
                return
            
            print(f"\nОригиналы на {orig_lang.upper()}:")
            for t in originals[:10]:
                # Получаем количество ольфакторных предложений
                olfactory = self.db.olfactory.find(orig_lang, text_id=t['id'])
                print(f"   [{t['id']}] {t['title']} - {t['author']} [{len(olfactory)}]")
            try:
                orig_id = int(input("ID оригинала: "))
            except:
                print("❌ Неверный ID")
                return
        
        # --- Путь к файлу ---
        file_path = input("Путь к файлу: ").strip()
        if not file_path:
            return
        
        # --- Метаданные ---
        if file_type == 'original':
            title, author, translator, year = self._ask_metadata()
        else:
            title, author, translator, year = self._ask_metadata(ask_translator=True)
        lang = self._select_language()
        
        # --- Загрузка ---
        try:
            result = self.processor.process_file(
                file_path=file_path,
                title=title,
                author=author,
                translator=translator,
                year=year,
                language=lang,
                is_original=(file_type == 'original'),
                original_lang=orig_lang,
                original_id=orig_id
            )

            print(f"   ID текста: {result['text_id']}")
            print(f"   Всего предложений: {result['total_sentences']}")
            print(f"   Ольфакторных предложений: {result['olfactory_sentences']}")

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
        print(f"\nЗагружено: {successful} из {len(files)}")
        print(f"Всего ольфакторных предложений: {total_smells}")

    def load_parallel_files(self):
        print("\n ЗАГРУЗКА ПАРЫ ТЕКСТОВ")
        
        orig_file = input("Путь к файлу оригинала: ").strip()
        trans_file = input("Путь к файлу перевода: ").strip()
        
        title, author, translator, year = self._ask_metadata(ask_translator=True)
        
        orig_lang = self._select_language("Язык оригинала: ")
        trans_lang = self._select_language("Язык перевода: ")
        
        print("\n🔄 Загрузка оригиналa...")
        orig_result = self.processor.process_file(
            file_path=orig_file,
            title=title,
            author=author,
            year=year,
            language=orig_lang,
            is_original=True
        )
        
        print("\n🔄 Загрузка перевода...")
        trans_result = self.processor.process_file(
            file_path=trans_file,
            title=title,
            author=author,
            year=year,
            translator=translator,
            language=trans_lang,
            is_original=False,
            original_lang=orig_lang,
            original_id=orig_result['text_id']
        )
        
        print(f"\n✅ Готово!")
        print(f"   Оригинал ID: {orig_result['text_id']} (👃 {orig_result['olfactory_sentences']} предложений)")
        print(f"   Перевод ID: {trans_result['text_id']} (👃 {trans_result['olfactory_sentences']} предложений)")

    def reanalyze_text(self):
        print("\nПОВТОРНЫЙ АНАЛИЗ ТЕКСТА")
        lang = self._select_language()
        try:
            text_id = int(input("ID текста: "))
        except:
            print("❌ Неверный ID")
            return
        
        result = self.processor.reanalyze_text(text_id, lang)
        if result:
            print(f"\n Добавлено {len(result)} новых ольфакторных предложений")

    # ==================== ВЫРАВНИВАНИЕ ====================

    def alignment_menu(self):
        while True:
            self.clear_screen()
            self.print_header()
            print("\n🔗 ВЫРАВНИВАНИЕ ОЛЬФАКТОРНЫХ ПРЕДЛОЖЕНИЙ:")
            print("  [1] Показать доступные пары текстов")
            print("  [2] Экспорт в Excel (для ручного выравнивания)")
            print("  [3] Импорт из Excel (после выравнивания)")
            print("  [4] Экспорт CSV (выровненные данные)")
            print("  [0] Назад")
            
            choice = input("\n👉 Выбор: ").strip()
            
            if choice == "1":
                self.show_alignable_pairs()
            
            elif choice == "2":
                try:
                    ru_id = int(input("ID русского текста: "))
                    en_id = int(input("ID английского перевода: "))
                except ValueError:
                    print("❌ Неверный ID")
                    continue
                
                output_path = input("Путь для сохранения (Enter - по умолчанию): ").strip()
                if not output_path:
                    output_path = f"data/csv/alignment_{ru_id}_to_{en_id}.xlsx" 
                
                result = self.db.alignment.export_for_alignment(
                    ru_text_id=ru_id,
                    en_text_id=en_id,
                    output_path=output_path
                )
                print(f"\n✅ Шаблон создан: {result}")
                
            elif choice == "3":
                excel_path = input("Путь к Excel файлу: ").strip()
                if not excel_path:
                    continue
                
                try:
                    ru_id = int(input("ID русского текста (Enter - пропустить): ") or 0)
                    en_id = int(input("ID английского текста (Enter - пропустить): ") or 0)
                except ValueError:
                    print("❌ Неверный ID")
                    continue
                
                clear = input("Очистить существующие выравнивания? (y/n): ").lower() == 'y'
                
                self.db.alignment.import_alignment_from_excel(
                    excel_path=excel_path,
                    ru_text_id=ru_id if ru_id else None,
                    en_text_id=en_id if en_id else None,
                    clear_existing=clear
                )
                
            elif choice == "4":
                output_path = input("Путь для сохранения CSV: ").strip()
                if not output_path:
                    output_path = "data/csv/aligned_data.csv"
                
                try:
                    ru_id = int(input("ID русского текста (Enter - все): ") or 0)
                    en_id = int(input("ID английского текста (Enter - все): ") or 0)
                except ValueError:
                    print("❌ Неверный ID")
                    continue
                
                self.db.csv.export_aligned_data(
                    output_path,
                    ru_text_id=ru_id if ru_id else None,
                    en_text_id=en_id if en_id else None
                )
                print(f"✅ CSV сохранен: {output_path}")
                
            elif choice == "0":
                break
            
            input("\n⏎ Нажми Enter для продолжения...")

    def show_alignable_pairs(self):
        """Показывает пары текстов, которые можно выровнять"""
        print("\n📚 ПАРЫ ТЕКСТОВ ДЛЯ ВЫРАВНИВАНИЯ:")
        print("=" * 70)
        
        # Получаем все русские тексты
        ru_texts = self.db.texts.get_by_language('ru', 'original')
        
        if not ru_texts:
            print("❌ Нет русских оригиналов")
            return
        
        found = False
        for ru_text in ru_texts:
            # Получаем переводы этого текста
            translations = self.db.texts.get_translations('ru', ru_text['id'])
            
            if translations:
                # Получаем количество ольфакторных предложений в русском
                ru_olfactory = self.db.olfactory.find('ru', text_id=ru_text['id'])
                ru_count = len(ru_olfactory)
                
                if ru_count == 0:
                    continue
                
                found = True
                print(f"\n🇷🇺 [{ru_text['id']}] {ru_text['title']} - {ru_text['author']} (👃 {ru_count})")
                
                for en_text in translations:
                    # Получаем количество ольфакторных предложений в английском
                    en_olfactory = self.db.olfactory.find('en', text_id=en_text['id'])
                    en_count = len(en_olfactory)
                    
                    # Просто показываем, что можно выровнять, без подсчета уже выровненных
                    print(f"   🇬🇧 [{en_text['id']}] {en_text['title']} - {en_text['author']} (👃 {en_count})")
        
        if not found:
            print("❌ Нет пар с ольфакторными предложениями")

    # ==================== СТАТИСТИКА ====================
    
    # def stats_menu(self):
    #     """Меню статистики"""
    #     self.clear_screen()
    #     self.print_header()
        
    #     print("\n📊 ОБЩАЯ СТАТИСТИКА:")
    #     print("=" * 40)
        
    #     total_texts = 0
    #     total_olfactory = 0
    #     total_verified = 0
    #     total_aligned = 0
        
    #     for lang in self.supported_languages:
    #         texts = self.db.texts.get_by_language(lang)
    #         lang_texts = len(texts)
    #         total_texts += lang_texts
            
    #         lang_olfactory = 0
    #         lang_verified = 0
    #         lang_aligned = 0
            
    #         for t in texts:
    #             olfactory = self.db.olfactory.get_by_text(lang, t['id'])
    #             lang_olfactory += len(olfactory)
    #             lang_verified += sum(1 for o in olfactory if o['verified'])
    #             for o in olfactory:
    #                 if lang == 'ru' and self.db.olfactory.get_aligned_en(o['id']):
    #                     lang_aligned += 1
            
    #         total_olfactory += lang_olfactory
    #         total_verified += lang_verified
    #         total_aligned += lang_aligned
            
    #         lang_symbol = self._get_lang_symbol(lang)
    #         print(f"\n{lang_symbol} {lang.upper()}:")
    #         print(f"   Текстов: {lang_texts}")
    #         print(f"   👃 Ольфакторных предложений: {lang_olfactory}")
    #         print(f"   ✅ Проверенных: {lang_verified}")
    #         if lang == 'ru':
    #             print(f"   🔗 Выровненных с переводом: {lang_aligned}")
        
    #     print("\n" + "=" * 40)
    #     print(f"📈 ВСЕГО:")
    #     print(f"   Текстов: {total_texts}")
    #     print(f"   👃 Ольфакторных предложений: {total_olfactory}")
    #     print(f"   ✅ Проверенных: {total_verified}")
    #     print(f"   🔗 Выровненных пар: {total_aligned}")
        
    #     input("\n⏎ Нажми Enter для продолжения...")

    # ==================== ЗАПУСК ====================
        
    def run(self):
        """Запуск консоли"""
        while self.running:
            self.clear_screen()
            self.print_header()
            self.print_menu()
            
            choice = input("\n👉 Выбор: ").strip()

            if choice == "1":
                self.files_menu()
            elif choice == "2":
                self.alignment_menu()
            elif choice == "3":
                self.stats_menu()
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