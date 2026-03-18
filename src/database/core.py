import sqlite3

class Database:
    """Только подключение к БД и выполнение запросов"""
    
    def __init__(self, path):
        self.path = path
        self.conn = None
    
    def connect(self):
        """Открывает соединение"""
        if not self.conn:
            self.conn = sqlite3.connect(self.path)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def close(self):
        """Закрывает соединение"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def execute(self, sql, params=None):
        """Выполняет запрос и возвращает результат"""
        conn = self.connect()
        cur = conn.cursor()
        
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            
            conn.commit()
            
            # Для SELECT возвращаем список словарей
            if sql.strip().upper().startswith('SELECT'):
                return [dict(row) for row in cur.fetchall()]
            
            # Для INSERT возвращаем id
            if sql.strip().upper().startswith('INSERT'):
                return cur.lastrowid
            
            # Для остальных возвращаем количество измененных строк
            return cur.rowcount
            
        except Exception as e:
            conn.rollback()
            raise e