# src/grammar.py
"""
UD-парсинг ольфакторных концептов.

Функции:
    parse_ru(text) -> str        — Stanza (ru_syntagrus), строковый формат
    parse_en(text) -> str        — spaCy (en_core_web_sm), строковый формат
    to_gram_json(gram_str) -> dict  — структурированные признаки из gram_structure

Формат gram_structure:
    ROOT[UPOS](лемма) + deprel(форма/UPOS) + deprel(форма/UPOS > [inner...])

Формат gram_json:
    {
        "root_pos":   "VERB",
        "root_lemma": "пахнуть",
        "deprels":    ["nsubj", "obl"],
        "has_nsubj":  true,
        "has_obj":    false,
        "has_obl":    true,
        "has_nmod":   false,
        "has_amod":   false,
        "has_acl":    false,
        "has_advmod": false,
        "has_conj":   false,
        "has_prep_of": false,
        "depth_gte2": false
    }
"""

import json
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
        # proxies={} отключает SOCKS-прокси, который stanza подхватывает из системы
        # и передаёт в requests — без PySocks это вызывает InvalidSchema.
        _nlp_ru = stanza.Pipeline(
            lang="ru",
            processors="tokenize,pos,lemma,depparse",
            tokenize_no_ssplit=True,
            verbose=False,
            download_method=stanza.DownloadMethod.REUSE_RESOURCES,
            proxies={},
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


# ── Извлечение структурированных признаков ────────────────────────────────────

_RE_ROOT = re.compile(r"ROOT\[([A-Z]+)\]\(([^)]+)\)")
_RE_DEPREL = re.compile(r"\b([a-z_]+)\(")


def to_gram_json(gram_str: str) -> dict:
    """
    Преобразует строку gram_structure в структурированный словарь признаков.

    Пример входа:
        "ROOT[VERB](пахнуть) + nsubj(запах/NOUN) + obl(комнате/NOUN > [case(в/ADP)])"

    Пример выхода:
        {"root_pos": "VERB", "root_lemma": "пахнуть", "deprels": ["nsubj", "obl", "case"],
         "has_nsubj": true, "has_obj": false, ...}
    """
    empty = {
        "root_pos": None, "root_lemma": None, "deprels": [],
        "has_nsubj": False, "has_obj": False, "has_obl": False,
        "has_nmod": False, "has_amod": False, "has_acl": False,
        "has_advmod": False, "has_conj": False, "has_prep_of": False,
        "depth_gte2": False,
    }

    if not gram_str or str(gram_str).strip() in ("", "nan"):
        return empty

    s = str(gram_str)

    root_m = _RE_ROOT.search(s)
    root_pos = root_m.group(1) if root_m else None
    root_lemma = root_m.group(2) if root_m else None

    # Все deprel-метки в строке (кроме ROOT)
    deprels = [d for d in _RE_DEPREL.findall(s) if d.upper() != "ROOT"]

    return {
        "root_pos":    root_pos,
        "root_lemma":  root_lemma,
        "deprels":     deprels,
        "has_nsubj":   "nsubj"  in deprels,
        "has_obj":     "obj"    in deprels,
        "has_obl":     "obl"    in deprels,
        "has_nmod":    "nmod"   in deprels,
        "has_amod":    "amod"   in deprels,
        "has_acl":     "acl"    in deprels,
        "has_advmod":  "advmod" in deprels,
        "has_conj":    "conj"   in deprels,
        "has_prep_of": bool(re.search(r"prep\(of", s)),
        "depth_gte2":  s.count(">") >= 1,
    }


def parse_to_json(gram_str: str) -> str:
    """Обёртка: возвращает to_gram_json как JSON-строку для записи в БД."""
    return json.dumps(to_gram_json(gram_str), ensure_ascii=False)
