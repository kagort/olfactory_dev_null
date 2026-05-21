# src/config.py
# пока нигде не используется
import os
from pathlib import Path

# Пути
PROJECT_ROOT = Path(__file__).parent.parent

DB_PATH = PROJECT_ROOT / "db" / "olfactory.db"

SCHEMAS_DIR = PROJECT_ROOT / "db" / "schemas"
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
BACKUP_DIR = PROJECT_ROOT / "db" / "backups"

# Создаем папки, если их нет
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Пути к данным
DATA_DIR = PROJECT_ROOT / "data" / "books" / "raw"
CSV_PATH = PROJECT_ROOT / "data" / "metadata.csv"

# результаты
# Путь для сохранения
ALIGNMENT_FILE = PROJECT_ROOT / "results" / "alignment.xlsx"


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


# Параметры БД
DB_CONFIG = {
    'database': str(DB_PATH),
    'timeout': 10,  # секунд
    'check_same_thread': False
}