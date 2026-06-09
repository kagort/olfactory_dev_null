# src/grammar.py
"""
UD-парсинг ольфакторных концептов.

Функции:
    parse_ru(text) -> str   — Stanza (ru_syntagrus)
    parse_en(text) -> str   — spaCy (en_core_web_sm)

Формат вывода:
    ROOT[UPOS](лемма) + deprel(форма/UPOS) + deprel(форма/UPOS > [inner...])
"""

import re
import spacy
import stanza

_nlp_en = None
_nlp_ru = None


def _get_nlp_en():
    global _nlp_en
    if _nlp_en is None:
        _nlp_en = spacy.load("en_core_web_sm")
    return _nlp_en


def _get_nlp_ru():
    global _nlp_ru
    if _nlp_ru is None:
        _nlp_ru = stanza.Pipeline(
            lang="ru",
            processors="tokenize,pos,lemma,depparse",
            tokenize_no_ssplit=True,
            verbose=False,
        )
    return _nlp_ru


def _fmt_deprel(label: str) -> str:
    """Нормализует deprel: сохраняет подтип только для значимых меток."""
    keep = {"nsubj", "obj", "obl", "nmod", "acl", "advcl", "csubj"}
    parts = label.split(":")
    return label if parts[0] in keep and len(parts) > 1 else parts[0]


def parse_ru(text: str, max_depth: int = 2) -> str:
    """
    Парсит русский текст через Stanza (ru_syntagrus).

    Возвращает строку вида:
      ROOT[UPOS](лемма) + deprel(форма/UPOS) + ...
    Вложенные зависимые (глубина ≤ max_depth):
      deprel(форма/UPOS > [inner_dep(форма/UPOS), ...])
    """
    if not text or not str(text).strip():
        return ""
    text = str(text).strip().rstrip(".")
    doc = _get_nlp_ru()(text)
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
            rel = _fmt_deprel(kid.deprel or "dep")
            grandkids = [gc for gc in sorted(children.get(kid.id, []), key=lambda x: x.id)
                         if (gc.upos or "X") != "PUNCT"]
            if grandkids and depth < max_depth:
                inner = ", ".join(
                    f"{_fmt_deprel(gc.deprel or 'dep')}({gc.text}/{gc.upos})"
                    for gc in grandkids
                )
                parts.append(f"{rel}({kid.text}/{kid.upos} > [{inner}])")
            else:
                parts.append(f"{rel}({kid.text}/{kid.upos})")
        label = "ROOT" if w == root_word else _fmt_deprel(w.deprel or "dep").upper()
        base = f"{label}[{w.upos or 'X'}]({w.lemma or w.text})"
        return (base + " + " + " + ".join(parts)) if parts else base

    return subtree(root_word) or text


def parse_en(text: str, max_depth: int = 2) -> str:
    """
    Парсит английский текст через spaCy (en_core_web_sm).
    Нотация идентична parse_ru.
    """
    if not text or not str(text).strip():
        return ""
    text = str(text).strip().rstrip(".")
    doc = _get_nlp_en()(text)

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
            rel = _fmt_deprel(kid.dep_)
            grandkids = [gc for gc in sorted(children.get(kid.i, []), key=lambda x: x.i)
                         if gc.pos_ not in ("PUNCT", "SPACE")]
            if grandkids and depth < max_depth:
                inner = ", ".join(
                    f"{_fmt_deprel(gc.dep_)}({gc.text}/{gc.pos_})"
                    for gc in grandkids
                )
                parts.append(f"{rel}({kid.text}/{kid.pos_} > [{inner}])")
            else:
                parts.append(f"{rel}({kid.text}/{kid.pos_})")
        label = "ROOT" if t == root_tok else _fmt_deprel(t.dep_).upper()
        base = f"{label}[{t.pos_}]({t.lemma_})"
        return (base + " + " + " + ".join(parts)) if parts else base

    return subtree(root_tok) or text
