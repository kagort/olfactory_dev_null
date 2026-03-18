"""
Класс для исследований - все графики и анализ в одном месте
Адаптирован под вашу структуру (без tokens, с olfactory)
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
from collections import Counter
from pathlib import Path
from src.database import OlfactoryDB

class OlfactoryResearch:
    """Класс для исследований - пишешь один раз, пользуешься всегда"""
    
    def __init__(self, db_path="data/olfactory.db"):
        self.db = OlfactoryDB(db_path)
        # Берем языки из TextManager, чтобы всегда совпадало
        self.languages = self.db.texts.languages
    
    def get_texts_dataframe(self, language=None):
        """Получить все тексты как pandas DataFrame"""
        texts = []
        
        if language:
            # Получаем тексты одного языка
            lang_texts = self.db.texts.get_by_language(language)
            for t in lang_texts:
                t['language'] = language
                texts.append(t)
        else:
            # Получаем тексты всех языков
            for lang in self.languages:
                lang_texts = self.db.texts.get_by_language(lang)
                for t in lang_texts:
                    t['language'] = lang
                    texts.append(t)
        
        df = pd.DataFrame(texts)
        
        if len(df) == 0:
            print("⚠️ Нет текстов в базе")
            return df
        
        # Добавляем информацию о запахах
        smell_counts = []
        
        for _, row in df.iterrows():
            olfactory = self.db.olfactory.get_by_text(row['language'], row['id'])
            smell_counts.append(len(olfactory))
        
        df['smell_count'] = smell_counts
        df['token_count'] = 0  # заглушка, если нет данных о токенах
        df['smell_ratio'] = 0  # заглушка
        
        return df
    
    def get_smells_dataframe(self, language=None):
        """Получить все запахи как DataFrame"""
        all_smells = []
        
        languages = [language] if language else self.languages
        
        for lang in languages:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                olfactory = self.db.olfactory.get_by_text(lang, text['id'])
                for o in olfactory:
                    if o['smell_words']:
                        # Парсим JSON если нужно
                        if isinstance(o['smell_words'], str):
                            try:
                                words = json.loads(o['smell_words'])
                            except:
                                words = []
                        else:
                            words = o['smell_words']
                        
                        for w in words:
                            if isinstance(w, dict):
                                all_smells.append({
                                    'text_id': text['id'],
                                    'title': text['title'],
                                    'author': text['author'],
                                    'language': lang,
                                    'word': w.get('word', '?'),
                                    'lemma': w.get('lemma', '?'),
                                    'pos': w.get('pos', '?'),
                                    'position_in_sentence': w.get('position', 0)
                                })
                            else:
                                all_smells.append({
                                    'text_id': text['id'],
                                    'title': text['title'],
                                    'author': text['author'],
                                    'language': lang,
                                    'word': str(w),
                                    'lemma': str(w),
                                    'pos': 'UNKNOWN',
                                    'position_in_sentence': 0
                                })
        
        return pd.DataFrame(all_smells)
    
    def plot_smell_distribution(self, language=None):
        """График распределения запахов"""
        df = self.get_texts_dataframe(language)
        
        if len(df) == 0:
            print("❌ Нет данных для графика")
            return
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        
        # Количество запахов по текстам
        df['smell_count'].hist(ax=axes[0], bins=20, color='skyblue', edgecolor='black')
        axes[0].set_title('Распределение количества запахов')
        axes[0].set_xlabel('Количество запахов')
        axes[0].set_ylabel('Количество текстов')
        
        # Тексты с наибольшим количеством запахов
        top10 = df.nlargest(10, 'smell_count')
        if len(top10) > 0:
            labels = [f"{row['title'][:20]}..." for _, row in top10.iterrows()]
            axes[1].barh(range(len(top10)), top10['smell_count'], color='lightcoral')
            axes[1].set_title('Топ-10 текстов по запахам')
            axes[1].set_yticks(range(len(top10)))
            axes[1].set_yticklabels(labels)
            axes[1].set_xlabel('Количество запахов')
        
        # Соотношение (заглушка, так как нет token_count)
        if len(df) > 1:
            axes[2].scatter(range(len(df)), df['smell_count'], alpha=0.5, c='green')
            axes[2].set_xlabel('Индекс текста')
            axes[2].set_ylabel('Слов-запахов')
            axes[2].set_title('Распределение запахов')
        
        plt.tight_layout()
        plt.show()
    
    def plot_top_smells(self, language=None, n=20):
        """Топ-N самых частых запахов"""
        smells_df = self.get_smells_dataframe(language)
        
        if len(smells_df) == 0:
            print("❌ Нет данных о запахах")
            return
        
        top_smells = smells_df['word'].value_counts().head(n)
        
        plt.figure(figsize=(12, 6))
        top_smells.plot(kind='bar', color='purple')
        plt.title(f'Топ-{n} самых частых запахов')
        plt.xlabel('Слово')
        plt.ylabel('Количество упоминаний')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
        
        return top_smells
    
    def compare_languages(self):
        """Сравнение языков"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        data = {}
        for lang in self.languages:
            df = self.get_texts_dataframe(lang)
            if len(df) > 0:
                data[lang] = df
        
        if not data:
            print("❌ Нет данных")
            return
        
        # Подготовка данных
        labels = [lang.upper() for lang in data.keys()]
        colors = ['blue', 'red', 'green', 'orange'][:len(labels)]
        
        # Среднее количество запахов
        means = [df['smell_count'].mean() for df in data.values()]
        axes[0, 0].bar(labels, means, color=colors)
        axes[0, 0].set_title('Среднее количество запахов в тексте')
        
        # Максимальное количество запахов
        maxs = [df['smell_count'].max() for df in data.values()]
        axes[0, 1].bar(labels, maxs, color=colors)
        axes[0, 1].set_title('Максимальное количество запахов')
        
        # Общее количество запахов
        sums = [df['smell_count'].sum() for df in data.values()]
        axes[1, 0].bar(labels, sums, color=colors)
        axes[1, 0].set_title('Всего упоминаний запахов')
        
        # Процент текстов с запахами
        percentages = [(df['smell_count'] > 0).mean() * 100 for df in data.values()]
        axes[1, 1].bar(labels, percentages, color=colors)
        axes[1, 1].set_title('Процент текстов, содержащих запахи')
        axes[1, 1].set_ylabel('Процент')
        
        plt.tight_layout()
        plt.show()
    
    def search_by_smell(self, smell_word, language=None):
        """Найти все тексты с конкретным запахом"""
        results = []
        
        languages = [language] if language else self.languages
        
        for lang in languages:
            texts = self.db.texts.get_by_language(lang)
            for text in texts:
                olfactory = self.db.olfactory.get_by_text(lang, text['id'])
                for o in olfactory:
                    if o['smell_words']:
                        if isinstance(o['smell_words'], str):
                            try:
                                words = json.loads(o['smell_words'])
                            except:
                                words = []
                        else:
                            words = o['smell_words']
                        
                        for w in words:
                            w_text = w.get('word', str(w)) if isinstance(w, dict) else str(w)
                            if smell_word.lower() in w_text.lower():
                                text_copy = dict(text)
                                text_copy['language'] = lang
                                text_copy['matched_word'] = w_text
                                text_copy['sentence'] = o['sentence']
                                results.append(text_copy)
                                break
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.drop_duplicates(subset=['id', 'language'])
        
        print(f"🔍 Найдено текстов с запахом '{smell_word}': {len(df)}")
        return df
    
    def get_smell_statistics_by_author(self, author, language=None):
        """Статистика запахов по конкретному автору"""
        texts = []
        
        languages = [language] if language else self.languages
        
        for lang in languages:
            author_texts = self.db.texts.get_by_author(author, lang)
            for t in author_texts:
                t['language'] = lang
                texts.append(t)
        
        if not texts:
            print(f"❌ Автор {author} не найден")
            return None
        
        results = []
        for text in texts:
            olfactory = self.db.olfactory.get_by_text(text['language'], text['id'])
            for o in olfactory:
                if o['smell_words']:
                    if isinstance(o['smell_words'], str):
                        try:
                            words = json.loads(o['smell_words'])
                        except:
                            words = []
                    else:
                        words = o['smell_words']
                    
                    for w in words:
                        w_text = w.get('word', str(w)) if isinstance(w, dict) else str(w)
                        results.append({
                            'title': text['title'],
                            'year': text['year'],
                            'language': text['language'],
                            'smell_word': w_text,
                            'sentence': o['sentence']
                        })
        
        df = pd.DataFrame(results)
        
        print(f"\n📊 Статистика для {author}:")
        print(f"   Всего произведений: {len(texts)}")
        print(f"   Всего слов-запахов: {len(df)}")
        
        if len(df) > 0:
            print(f"\nТоп-10 запахов у автора:")
            print(df['smell_word'].value_counts().head(10))
        
        return df
    
    def export_to_csv(self, table_name, output_file):
        """Экспортировать любую таблицу в CSV"""
        try:
            # Пробуем разные варианты получения данных
            if table_name.startswith('texts_'):
                lang = table_name.split('_')[1]
                data = self.db.texts.get_by_language(lang)
            elif table_name.startswith('olfactory_'):
                lang = table_name.split('_')[1]
                texts = self.db.texts.get_by_language(lang)
                data = []
                for t in texts:
                    olfactory = self.db.olfactory.get_by_text(lang, t['id'])
                    for o in olfactory:
                        o_copy = dict(o)
                        o_copy['text_title'] = t['title']
                        o_copy['text_author'] = t['author']
                        data.append(o_copy)
            else:
                # Прямой SQL запрос
                data = self.db.db.execute(f"SELECT * FROM {table_name}")
            
            df = pd.DataFrame(data)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"✅ Экспортировано {len(df)} записей в {output_file}")
            
        except Exception as e:
            print(f"❌ Ошибка экспорта: {e}")