"""
Анализатор параллельных RU-EN предложений.
Может работать как с Excel, так и с БД.
Не зависит от research.py, можно использовать отдельно.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import spacy
import stanza
from sentence_transformers import SentenceTransformer
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

class ParallelAnalyzer:
    """
    Анализ параллельного корпуса RU-EN:
    - UD-парсинг (Stanza для RU, spaCy для EN)
    - LaBSE similarity
    - Классификация переводческих сдвигов
    """
    
    def __init__(self):
        print("🔄 Загрузка моделей...")
        
        # LaBSE для сходства
        self.similarity_model = SentenceTransformer('sentence-transformers/LaBSE')
        
        # spaCy для EN
        self.nlp_en = spacy.load("en_core_web_trf")
        
        # Stanza для RU
        stanza.download("ru", verbose=False)
        self.nlp_ru = stanza.Pipeline(
            "ru",
            processors="tokenize,pos,lemma,depparse",
            tokenize_no_ssplit=True,
            verbose=False
        )
        
        # Пороги классификации
        self.THRESHOLD_EQUIV = 0.90
        self.THRESHOLD_SHIFT = 0.75
        
        print("✅ Модели загружены")
    
    # === 1. UD-парсинг ===
    
    def _fmt_deprel(self, label: str) -> str:
        """Нормализует deprel"""
        keep = {"nsubj", "obj", "obl", "nmod", "acl", "advcl", "csubj"}
        parts = label.split(":")
        return label if parts[0] in keep and len(parts) > 1 else parts[0]
    
    def parse_ru(self, text: str, max_depth: int = 2) -> str:
        """UD-структура для русского (Stanza)"""
        if not text or not str(text).strip():
            return ""
        text = str(text).strip().rstrip(".")
        doc = self.nlp_ru(text)
        if not doc.sentences:
            return text
        
        words = doc.sentences[0].words
        children = {w.id: [] for w in words}
        root_word = None
        
        for w in words:
            if w.deprel and w.deprel.lower() == "root":
                root_word = w
            if w.head and w.head in children and w.head != w.id:
                children[w.head].append(w)
        
        if root_word is None:
            root_word = words[0]
        
        def subtree(w, depth=0):
            if (w.upos or "X") == "PUNCT":
                return None
            kids = [c for c in sorted(children.get(w.id, []), key=lambda x: x.id)
                    if (c.upos or "X") != "PUNCT"]
            parts = []
            for kid in kids:
                rel = self._fmt_deprel(kid.deprel or "dep")
                grandkids = [gc for gc in sorted(children.get(kid.id, []), key=lambda x: x.id)
                             if (gc.upos or "X") != "PUNCT"]
                if grandkids and depth < max_depth:
                    inner = ", ".join(f"{self._fmt_deprel(gc.deprel or 'dep')}({gc.text}/{gc.upos})"
                                      for gc in grandkids)
                    parts.append(f"{rel}({kid.text}/{kid.upos} > [{inner}])")
                else:
                    parts.append(f"{rel}({kid.text}/{kid.upos})")
            label = "ROOT" if w == root_word else self._fmt_deprel(w.deprel or "dep").upper()
            base = f"{label}[{w.upos or 'X'}]({w.lemma or w.text})"
            return (base + " + " + " + ".join(parts)) if parts else base
        
        return subtree(root_word) or text
    
    def parse_en(self, text: str, max_depth: int = 2) -> str:
        """UD-структура для английского (spaCy)"""
        if not text or not str(text).strip():
            return ""
        text = str(text).strip().rstrip(".")
        doc = self.nlp_en(text)
        
        children = {t.i: [] for t in doc}
        root_tok = None
        for t in doc:
            if t.dep_ == "ROOT":
                root_tok = t
            if t.dep_ != "ROOT" and t.head.i != t.i:
                children[t.head.i].append(t)
        if root_tok is None:
            root_tok = doc[0]
        
        def subtree(t, depth=0):
            if t.pos_ in ("PUNCT", "SPACE"):
                return None
            kids = [c for c in sorted(children.get(t.i, []), key=lambda x: x.i)
                    if c.pos_ not in ("PUNCT", "SPACE")]
            parts = []
            for kid in kids:
                rel = self._fmt_deprel(kid.dep_)
                grandkids = [gc for gc in sorted(children.get(kid.i, []), key=lambda x: x.i)
                             if gc.pos_ not in ("PUNCT", "SPACE")]
                if grandkids and depth < max_depth:
                    inner = ", ".join(f"{self._fmt_deprel(gc.dep_)}({gc.text}/{gc.pos_})"
                                      for gc in grandkids)
                    parts.append(f"{rel}({kid.text}/{kid.pos_} > [{inner}])")
                else:
                    parts.append(f"{rel}({kid.text}/{kid.pos_})")
            label = "ROOT" if t == root_tok else self._fmt_deprel(t.dep_).upper()
            base = f"{label}[{t.pos_}]({t.lemma_})"
            return (base + " + " + " + ".join(parts)) if parts else base
        
        return subtree(root_tok) or text
    
    # === 2. LaBSE similarity ===
    
    def compute_similarity(self, ru_text: str, en_text: str) -> float:
        """Косинусное сходство между RU и EN фразами"""
        emb_ru = self.similarity_model.encode([str(ru_text).strip()], normalize_embeddings=True)
        emb_en = self.similarity_model.encode([str(en_text).strip()], normalize_embeddings=True)
        return float((emb_ru * emb_en).sum())
    
    # === 3. Классификация сдвигов ===
    
    def classify_shift(self, cos: float, type_ru: str = None, type_en: str = None,
                      tone_ru: str = None, tone_en: str = None,
                      conn_ru: str = None, conn_en: str = None) -> dict:
        """
        Классификация переводческого сдвига
        Возвращает: label, notes, needs_review
        """
        type_ru = type_ru or ''
        type_en = type_en or ''
        tone_ru = tone_ru or ''
        tone_en = tone_en or ''
        conn_ru = conn_ru or ''
        conn_en = conn_en or ''
        
        type_match = (type_ru == type_en)
        tone_match = (tone_ru == tone_en)
        conn_match = (conn_ru == conn_en)
        all_match = type_match and tone_match and conn_match
        
        # Базовая категория
        if cos >= self.THRESHOLD_EQUIV:
            base = "equivalent" if all_match else "lex"
        elif cos >= self.THRESHOLD_SHIFT:
            base = "shift"
        else:
            base = "significant_shift"
        
        # Дополнительные метки
        extras = []
        if not type_match:
            extras.append(f"type_shift({type_ru}→{type_en})")
        if not tone_match:
            extras.append(f"tone_shift({tone_ru}→{tone_en})")
        if not conn_match:
            extras.append(f"conn_shift({conn_ru}→{conn_en})")
        
        label = base + (("+" + "+".join(extras)) if extras else "")
        
        # Заметки
        note_parts = [f"cos={cos:.3f}"]
        if not type_match:
            note_parts.append(f"type:{type_ru}→{type_en}")
        if not tone_match:
            note_parts.append(f"tone:{tone_ru}→{tone_en}")
        if not conn_match:
            note_parts.append(f"conn:{conn_ru}→{conn_en}")
        if len(note_parts) == 1:
            note_parts.append("все категории совпадают")
        
        notes = " | ".join(note_parts)
        
        # Флаг для проверки
        needs_review = (
            cos < 0.70
            or cos > 0.97
            or (cos >= self.THRESHOLD_EQUIV and not all_match)
            or base == "significant_shift"
        )
        
        return {
            'label': label,
            'notes': notes,
            'needs_review': needs_review,
            'cosine': cos
        }
    
    # === 4. Работа с Excel (как в Colab) ===
    
    def analyze_excel(self, input_path: str, output_path: str = None) -> str:
        """
        Полный анализ Excel-файла (как в Colab)
        Ожидает колонки: concept_unit_RU, concept_unit_EN, type_RU, type_EN,
                       connotation_RU, connotation_EN, тональность_RU, тональность_EN
        """
        print(f"📂 Чтение {input_path}...")
        df = pd.read_excel(input_path)
        
        print("🔄 Вычисление UD-структур и сходства...")
        results = []
        for idx, row in df.iterrows():
            if idx % 50 == 0:
                print(f"  строка {idx+1}/{len(df)}")
            
            ru_text = str(row.get('concept_unit_RU', '')).strip()
            en_text = str(row.get('concept_unit_EN', '')).strip()
            
            if not ru_text or not en_text or ru_text in ('None', 'nan'):
                continue
            
            # UD-парсинг
            ud_ru = self.parse_ru(ru_text)
            ud_en = self.parse_en(en_text)
            
            # Сходство
            cos = self.compute_similarity(ru_text, en_text)
            
            # Классификация
            shift = self.classify_shift(
                cos=cos,
                type_ru=row.get('type_RU'),
                type_en=row.get('type_EN'),
                tone_ru=row.get('тональность_RU'),
                tone_en=row.get('тональность_EN'),
                conn_ru=row.get('connotation_RU'),
                conn_en=row.get('connotation_EN')
            )
            
            results.append({
                **row.to_dict(),
                'ud_ru': ud_ru,
                'ud_en': ud_en,
                'cosine_sim_LaBSE': cos,
                'translation_shift': shift['label'],
                'shift_notes': shift['notes'],
                'needs_review': shift['needs_review']
            })
        
        df_result = pd.DataFrame(results)
        
        if not output_path:
            output_path = str(Path(input_path).with_suffix('')) + '_analyzed.xlsx'
        
        df_result.to_excel(output_path, index=False)
        print(f"✅ Сохранено в {output_path}")
        
        # Статистика
        print("\n📊 Статистика:")
        print(df_result['translation_shift'].str.split('+').str[0].value_counts())
        print(f"\n🔍 На проверку: {df_result['needs_review'].sum()} строк")
        
        return output_path
    
    # === 5. Работа с БД (опционально) ===
    
    def analyze_db_pairs(self, db, ru_ids: list = None, en_ids: list = None) -> pd.DataFrame:
        """
        Анализ пар из базы данных
        db - экземпляр OlfactoryDB
        """
        if ru_ids and en_ids and len(ru_ids) == len(en_ids):
            # Конкретные пары по ID
            pairs = list(zip(ru_ids, en_ids))
        else:
            # Все выровненные пары из БД
            pairs = db.db.execute("""
                SELECT a.ru_id, a.en_id, 
                       ru.sentence as ru_sent, ru.type as ru_type, ru.tonal as ru_tone, ru.connotation as ru_conn,
                       en.sentence as en_sent, en.type as en_type, en.tonal as en_tone, en.connotation as en_conn
                FROM olfactory_alignments a
                JOIN olfactory_ru ru ON a.ru_id = ru.id
                JOIN olfactory_en en ON a.en_id = en.id
            """)
            pairs = [(p['ru_id'], p['en_id']) for p in pairs]
        
        results = []
        for ru_id, en_id in pairs:
            ru = db.olfactory.get_by_id('ru', ru_id)
            en = db.olfactory.get_by_id('en', en_id)
            
            if not ru or not en:
                continue
            
            cos = self.compute_similarity(ru['sentence'], en['sentence'])
            shift = self.classify_shift(
                cos=cos,
                type_ru=ru.get('type'),
                type_en=en.get('type'),
                tone_ru=ru.get('tonal'),
                tone_en=en.get('tonal'),
                conn_ru=ru.get('connotation'),
                conn_en=en.get('connotation')
            )
            
            results.append({
                'ru_id': ru_id,
                'en_id': en_id,
                'ru_sentence': ru['sentence'],
                'en_sentence': en['sentence'],
                'ud_ru': self.parse_ru(ru['sentence']),
                'ud_en': self.parse_en(en['sentence']),
                'cosine_sim': cos,
                'shift_label': shift['label'],
                'shift_notes': shift['notes'],
                'needs_review': shift['needs_review']
            })
        
        return pd.DataFrame(results)


# Пример использования (раскомментировать при необходимости)
if __name__ == "__main__":
    analyzer = ParallelAnalyzer()
    
    # Тест
    ru = "В воздухе пахло яблоками"
    en = "The air smelled of apples"
    
    print(f"\n🇷🇺 {ru}")
    print(f"🇬🇧 {en}")
    print(f"UD RU: {analyzer.parse_ru(ru)}")
    print(f"UD EN: {analyzer.parse_en(en)}")
    print(f"Similarity: {analyzer.compute_similarity(ru, en):.4f}")