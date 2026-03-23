from .core import Database
from .managers import *

class OlfactoryDB:
    """Главный класс для работы с БД"""
    
    def __init__(self, path="data/olfactory.db"):
        self.db = Database(path)
        
        # Инициализируем менеджеры (обновленные)
        self.tables = TableManager(self.db)
        self.texts = TextManager(self.db)
        self.olfactory = OlfactoryManager(self.db)  
        self.csv = CsvExporter(self.db)
        self.alignment = AlignmentHelper(self.db)
        
        
    def init(self):
        """Создает все таблицы"""
        self.tables.create_all()
        print("✅ База данных готова")
    
    def close(self):
        """Закрывает соединение"""
        self.db.close()