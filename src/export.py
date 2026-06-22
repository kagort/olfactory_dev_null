"""
Экспорт для выравнивания - 4 независимых листа
Запуск: 
    python src/export.py --export alignment --ru 1 --en 1
    python src/export.py --export grammar --ru 1 --en 1
    python src/export.py --export concept --ru 1 --en 1
    python src/export.py --export sentiment --ru 1 --en 1
"""




# ── ФУНКЦИИ ДЛЯ КАЖДОГО ЛИСТА ─────────────────────────────────────────────

def export_alignment_sheet(ru_text_id, translation_id, output_path=ALIGNMENT_FILE, overwrite=False):
    """ЛИСТ 1: Выравнивание (с цветами)"""
    
    ru, en, align, ru_id_to_num, ru_num_to_text, _, _ = get_data(ru_text_id, translation_id)
    
    rows = []
    for _, row in en.iterrows():
        pair = align[align['sentence_en_id'] == row['sentence_id']]
        if not pair.empty:
            ru_num = ru_id_to_num.get(pair.iloc[0]['sentence_ru_id'], '')
            ru_text = ru_num_to_text.get(ru_num, '')
            sim = pair.iloc[0]['cosine_sim']
            auto = '✓' if pair.iloc[0]['auto_aligned'] == 1 else ('?' if pair.iloc[0]['auto_aligned'] == 2 else '')
        else:
            ru_num, ru_text, sim, auto = '', '', '', ''
        
        rows.append([row['en_num'], row['sentence'], ru_num, ru_text, sim, auto])
    
    # RU без пары
    ru_with_pair = set(align['sentence_ru_id'])
    for _, row in ru.iterrows():
        if row['sentence_id'] not in ru_with_pair:
            rows.append(['', '', row['ru_num'], row['sentence'], '', ''])
    
    df = pd.DataFrame(rows, columns=['EN №', 'EN Предложение', 'RU №', 'RU Предложение', 'cosine_sim', 'auto'])
    df['RU №'] = pd.to_numeric(df['RU №'], errors='coerce')
    df = df.sort_values('RU №', na_position='last').reset_index(drop=True)
    
    def format_func(ws, df):
        # Ширина
        widths = {'A': 8, 'B': 70, 'C': 8, 'D': 70, 'E': 12, 'F': 8}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        
        # Заголовки
        for cell in ws[1]:
            cell.fill = FILL_HEADER
            cell.font = FONT_HEADER
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Перенос
        for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        
        # Цвета
        for row in ws.iter_rows(min_row=2):
            auto_val = row[5].value
            if auto_val == '✓':
                for cell in row:
                    cell.fill = FILL_AUTO
            elif auto_val == '?':
                for cell in row:
                    cell.fill = FILL_SUGGESTED
    
    save_sheet(df, output_path, 'Выравнивание', format_func)
    return df


def export_grammar_sheet(ru_text_id, translation_id, output_path=ALIGNMENT_FILE, overwrite=False):
    """ЛИСТ 2: Грамматические структуры"""
    
    ru, en, align, ru_id_to_num, _, _, ru_num_to_grammar = get_data(ru_text_id, translation_id)
    
    rows = []
    for _, row in en.iterrows():
        pair = align[align['sentence_en_id'] == row['sentence_id']]
        if not pair.empty:
            ru_num = ru_id_to_num.get(pair.iloc[0]['sentence_ru_id'], '')
            ru_gram = ru_num_to_grammar.get(ru_num, '')
        else:
            ru_num, ru_gram = '', ''
        rows.append([row['en_num'], row['sentence'], row['gram_structure'], ru_num, ru_gram])
    
    df = pd.DataFrame(rows, columns=['EN №', 'EN Предложение', 'EN Грамматика', 'RU №', 'RU Грамматика'])
    df['RU №'] = pd.to_numeric(df['RU №'], errors='coerce')
    df = df.sort_values('RU №', na_position='last').reset_index(drop=True)
    
    def format_func(ws, df):
        widths = {'A': 8, 'B': 60, 'C': 30, 'D': 8, 'E': 30}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        
        for cell in ws[1]:
            cell.fill = FILL_HEADER
            cell.font = FONT_HEADER
        
        for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
    
    save_sheet(df, output_path, 'Грамматика', format_func)
    return df


def export_concept_sheet(ru_text_id, translation_id, output_path=ALIGNMENT_FILE, overwrite=False):
    """ЛИСТ 3: Концепт-юниты с грамматикой"""
    
    ru, en, align, ru_id_to_num, _, ru_num_to_concept, ru_num_to_grammar = get_data(ru_text_id, translation_id)
    
    rows = []
    for _, row in en.iterrows():
        pair = align[align['sentence_en_id'] == row['sentence_id']]
        if not pair.empty:
            ru_num = ru_id_to_num.get(pair.iloc[0]['sentence_ru_id'], '')
            ru_concept = ru_num_to_concept.get(ru_num, '')
            ru_gram = ru_num_to_grammar.get(ru_num, '')
        else:
            ru_num, ru_concept, ru_gram = '', '', ''
        rows.append([row['en_num'], row['sentence'], row['concept_phrase'], ru_num, ru_concept, ru_gram])
    
    df = pd.DataFrame(rows, columns=['EN №', 'EN Предложение', 'EN Концепт', 'RU №', 'RU Концепт', 'RU Грамматика'])
    df['RU №'] = pd.to_numeric(df['RU №'], errors='coerce')
    df = df.sort_values('RU №', na_position='last').reset_index(drop=True)
    
    def format_func(ws, df):
        widths = {'A': 8, 'B': 50, 'C': 25, 'D': 8, 'E': 25, 'F': 25}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        
        for cell in ws[1]:
            cell.fill = FILL_HEADER
            cell.font = FONT_HEADER
        
        for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
    
    save_sheet(df, output_path, 'Концепт-юниты', format_func)
    return df


def export_sentiment_sheet(ru_text_id, translation_id, output_path=ALIGNMENT_FILE, overwrite=False):
    """ЛИСТ 4: Сентимент-анализ"""
    
    ru, en, align, ru_id_to_num, _, _, _ = get_data(ru_text_id, translation_id)
    
    # Добавляем сентимент
    ru['sentiment'] = ru['sentence'].apply(sentiment_ru)
    en['sentiment'] = en['sentence'].apply(sentiment_en)
    
    ru_num_to_sent = dict(zip(ru['ru_num'], ru['sentiment']))
    
    rows = []
    for _, row in en.iterrows():
        pair = align[align['sentence_en_id'] == row['sentence_id']]
        if not pair.empty:
            ru_num = ru_id_to_num.get(pair.iloc[0]['sentence_ru_id'], '')
            ru_sent = ru_num_to_sent.get(ru_num, '')
        else:
            ru_num, ru_sent = '', ''
        rows.append([row['en_num'], row['sentence'], row['sentiment'], ru_num, ru_sent])
    
    df = pd.DataFrame(rows, columns=['EN №', 'EN Предложение', 'EN Сентимент', 'RU №', 'RU Сентимент'])
    df['RU №'] = pd.to_numeric(df['RU №'], errors='coerce')
    df = df.sort_values('RU №', na_position='last').reset_index(drop=True)
    
    def format_func(ws, df):
        widths = {'A': 8, 'B': 70, 'C': 15, 'D': 8, 'E': 15}
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
        
        for cell in ws[1]:
            cell.fill = FILL_HEADER
            cell.font = FONT_HEADER
        
        for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
    
    save_sheet(df, output_path, 'Сентимент', format_func)
    return df


# ── ИМПОРТ (только первого листа) ──────────────────────────────────────────

def import_alignment(excel_path=ALIGNMENT_FILE):
    """Импортирует выравнивание из первого листа обратно в БД"""
    
    if not Path(excel_path).exists():
        print(f"❌ Файл не найден: {excel_path}")
        return
    
    df = pd.read_excel(excel_path, sheet_name='Выравнивание')
    
    # Берем только строки с парой
    df_pairs = df[df['RU №'].notna() & df['EN №'].notna()].copy()
    df_pairs['RU №'] = df_pairs['RU №'].astype(int)
    df_pairs['EN №'] = df_pairs['EN №'].astype(int)
    
    print(f"📥 Импорт: {len(df_pairs)} пар")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем ID предложений по номерам
    ru_nums = tuple(df_pairs['RU №'].unique())
    en_nums = tuple(df_pairs['EN №'].unique())
    
    ru_id_map = pd.read_sql(
        f"SELECT sentence_id, row_number FROM sentences WHERE row_number IN {ru_nums}",
        conn
    )
    en_id_map = pd.read_sql(
        f"SELECT sentence_id, row_number FROM sentences WHERE row_number IN {en_nums}",
        conn
    )
    
    ru_num_to_id = dict(zip(ru_id_map['row_number'], ru_id_map['sentence_id']))
    en_num_to_id = dict(zip(en_id_map['row_number'], en_id_map['sentence_id']))
    
    stats = {'inserted': 0, 'already': 0, 'errors': 0}
    
    for _, row in df_pairs.iterrows():
        try:
            ru_id = ru_num_to_id.get(row['RU №'])
            en_id = en_num_to_id.get(row['EN №'])
            
            if not ru_id or not en_id:
                stats['errors'] += 1
                continue
            
            cursor.execute(
                "SELECT alignment_id FROM alignment WHERE sentence_ru_id=? AND sentence_en_id=?",
                (ru_id, en_id)
            )
            
            if cursor.fetchone():
                stats['already'] += 1
            else:
                cursor.execute(
                    "INSERT INTO alignment (sentence_ru_id, sentence_en_id, auto_aligned) VALUES (?,?,0)",
                    (ru_id, en_id)
                )
                stats['inserted'] += 1
                
        except Exception as e:
            print(f"   ⚠️ Ошибка: {e}")
            stats['errors'] += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Импорт завершен:")
    print(f"   Добавлено: {stats['inserted']}")
    print(f"   Уже было: {stats['already']}")
    print(f"   Ошибок: {stats['errors']}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Экспорт/импорт для выравнивания')
    parser.add_argument('--export', choices=['alignment', 'grammar', 'concept', 'sentiment', 'all'],
                       help='Какой лист экспортировать')
    parser.add_argument('--import', dest='import_mode', action='store_true',
                       help='Импортировать выравнивание из Excel')
    parser.add_argument('--ru', type=int, help='ID русского текста')
    parser.add_argument('--en', type=int, help='ID английского перевода')
    parser.add_argument('--file', type=str, default=str(ALIGNMENT_FILE),
                       help='Путь к файлу')
    parser.add_argument('--list', action='store_true', help='Список текстов')
    
    args = parser.parse_args()
    
    if args.list:
        conn = sqlite3.connect(DB_PATH)
        print("\n📚 Русские тексты:")
        ru = pd.read_sql("SELECT text_id, title FROM texts WHERE language='ru'", conn)
        for _, row in ru.iterrows():
            print(f"   {row['text_id']}: {row['title']}")
        print("\n🌐 Английские переводы:")
        en = pd.read_sql("SELECT translation_id, title FROM translations WHERE language='en'", conn)
        for _, row in en.iterrows():
            print(f"   {row['translation_id']}: {row['title']}")
        conn.close()
        return
    
    if args.import_mode:
        import_alignment(args.file)
        return
    
    if not args.export:
        parser.print_help()
        return
    
    if not args.ru or not args.en:
        print("❌ Укажите --ru и --en")
        return
    
    # Экспорт
    if args.export == 'alignment' or args.export == 'all':
        export_alignment_sheet(args.ru, args.en, args.file)
    if args.export == 'grammar' or args.export == 'all':
        export_grammar_sheet(args.ru, args.en, args.file)
    if args.export == 'concept' or args.export == 'all':
        export_concept_sheet(args.ru, args.en, args.file)
    if args.export == 'sentiment' or args.export == 'all':
        export_sentiment_sheet(args.ru, args.en, args.file)
    
    print(f"\n✅ Все готово! Файл: {args.file}")


if __name__ == "__main__":
    main()