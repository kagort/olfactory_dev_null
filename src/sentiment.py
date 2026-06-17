# src/sentiment.py
"""
Анализ тональности через локальные модели.

Модели (скачать вручную):
  RU: sismetanin/roberta-russian-sentiment → C:\models\roberta-russian-sentiment\
  EN: cardiffnlp/twitter-roberta-base-sentiment-latest → C:\models\twitter-roberta-sentiment\

Использование:
  from sentiment import sentiment_ru, sentiment_en
  label = sentiment_ru("пахло розами")  # → 'positiv'
  label = sentiment_en("smelled of roses")  # → 'positiv'
"""

from pathlib import Path

_PATHS = {
    'ru': r"C:\models\roberta-russian-sentiment",
    'en': r"C:\models\twitter-roberta-sentiment",
}

_LABEL_MAP_RU = {
    'POSITIVE': 'positiv',
    'NEGATIVE': 'negativ',
    'NEUTRAL':  'neutral',
    # roberta-russian-sentiment outputs: LABEL_0=neg, LABEL_1=neu, LABEL_2=pos
    'LABEL_0': 'negativ',
    'LABEL_1': 'neutral',
    'LABEL_2': 'positiv',
}
_LABEL_MAP_EN = {
    'LABEL_0': 'negativ',
    'LABEL_1': 'neutral',
    'LABEL_2': 'positiv',
    'negative': 'negativ',
    'neutral':  'neutral',
    'positive': 'positiv',
}

_pipelines = {}

def _get_pipeline(lang: str):
    if lang not in _pipelines:
        from transformers import pipeline
        path = _PATHS[lang]
        if not Path(path).exists():
            raise FileNotFoundError(
                f"Модель не найдена: {path}\n"
                f"Скачайте вручную с huggingface.co и положите в {path}"
            )
        _pipelines[lang] = pipeline("text-classification", model=path, local_files_only=True)
    return _pipelines[lang]


def _predict(text: str, lang: str, label_map: dict) -> str:
    try:
        pipe = _get_pipeline(lang)
        result = pipe(text[:512], truncation=True)[0]
        raw = result['label'].upper()
        return label_map.get(raw, label_map.get(result['label'], 'neutral'))
    except FileNotFoundError:
        raise
    except Exception:
        return 'neutral'


def sentiment_ru(text: str) -> str:
    return _predict(text, 'ru', _LABEL_MAP_RU)


def sentiment_en(text: str) -> str:
    return _predict(text, 'en', _LABEL_MAP_EN)


def is_available(lang: str) -> bool:
    return Path(_PATHS[lang]).exists()
