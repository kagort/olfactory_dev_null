from .core import Database
from .managers import TableManager, TextManager, OlfactoryManager  # ← изменили импорты

# Заглушка для словаря (если не используется)
class DummyDict:
    def check(self, word, language): return False
    def get_all(self, language=None): return []
    def add(self, word, language): return True


class OlfactoryDB:
    """Главный класс для работы с БД"""
    
    def __init__(self, path="data/olfactory.db"):
        self.db = Database(path)
        
        # Инициализируем менеджеры (обновленные)
        self.tables = TableManager(self.db)
        self.texts = TextManager(self.db)
        self.olfactory = OlfactoryManager(self.db)  # ← новый менеджер вместо sentences и olfactory_tokens
        
        # Заглушка для обратной совместимости
        self.dict = DummyDict()
    
    def init(self):
        """Создает все таблицы"""
        self.tables.create_all()
        print("✅ База данных готова")
    
    def close(self):
        """Закрывает соединение"""
        self.db.close()