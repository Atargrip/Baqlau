import pdfplumber
import re
import os
import json
from decimal import Decimal


def clean_amount(amount_str):
    """Превращает строку '1 158,00' -> 1158.00"""
    if not amount_str:
        return Decimal(0)
    # Удаляем пробелы, неразрывные пробелы (\xa0) и переносы строк
    clean = str(amount_str).replace(" ", "").replace("\xa0", "").replace("\n", "")
    clean = clean.replace(",", ".")
    try:
        return Decimal(clean)
    except:
        return Decimal(0)


def parse_halyk_bank(pdf):
    transactions = []

    # Настройки для поиска таблицы.
    # snap_tolerance: "прилипание" текста к ячейке
    # intersection_tolerance: терпимость к пересечению линий
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 4,
        "text_x_tolerance": 2,
        "text_y_tolerance": 2,
    }

    for page in pdf.pages:
        tables = page.extract_tables(table_settings)

        for table in tables:
            for row in table:
                # Очистка None значений
                clean_row = [str(cell) if cell else "" for cell in row]

                # Пропускаем короткие строки (в выписке Халыка обычно 7-8 колонок)
                if len(clean_row) < 4:
                    continue

                col_date = clean_row[0].replace("\n", " ")
                col_desc = clean_row[2].replace("\n", " ")
                col_amount = clean_row[3]

                # 1. Пропускаем заголовки
                if "Дата" in col_date or "проведения" in col_date:
                    continue
                # 2. Пропускаем "Всего", "Остаток"
                if "Всего" in col_date or "остаток" in col_date.lower():
                    continue
                # 3. Проверка валидности даты (DD.MM.YYYY)
                if not re.search(r'\d{2}\.\d{2}\.\d{4}', col_date):
                    continue

                # Извлечение данных
                amount = clean_amount(col_amount)

                # Если сумма 0 (информационная строка), можно пропускать или оставлять
                if amount == 0:
                    continue

                t_type = "expense" if amount < 0 else "income"

                transactions.append({
                    "date": col_date.split()[0],  # Берем только первую часть даты
                    "merchant": col_desc.strip(),
                    "amount": float(abs(amount)),  # Модуль числа для БД
                    "currency": clean_row[4].replace("\n", ""),
                    "type": t_type,
                    "bank": "Halyk Bank"
                })

    return transactions


def extract_finance_data(pdf_path):
    if not os.path.exists(pdf_path):
        return {"error": f"Файл не найден: {pdf_path}"}

    results = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                return {"error": "PDF пустой"}

            # Читаем текст первой страницы для определения банка
            first_page_text = pdf.pages[0].extract_text()

            # ДЕБАГ: Посмотрим, что видит питон (первые 200 символов)
            print("--- TEXT HEADER DEBUG ---")
            print(first_page_text[:200])
            print("-------------------------")

            if 'Народный Банк' in first_page_text or 'Halyk' in first_page_text or 'HSBK' in first_page_text:
                print("✅ Банк определен: Halyk Bank")
                results = parse_halyk_bank(pdf)

            elif 'Kaspi' in first_page_text:
                print("✅ Банк определен: Kaspi Gold (пока заглушка)")
                results = []  # Тут будет функция для каспи

            else:
                return {"error": "Банк не распознан. Проверьте ключевые слова."}

    except Exception as e:
        return {"error": f"Ошибка при чтении PDF: {str(e)}"}

    return results


if __name__ == "__main__":
    file_name = "C:/Users/Aset/Desktop/pdf_statements_1770648716012.pdf"  # Убедитесь, что имя файла верное!

    data = extract_finance_data(file_name)

    # ВАЖНО: Проверяем тип данных перед выводом
    if isinstance(data, list):
        print(f"Найдено транзакций: {len(data)}")
        if len(data) > 0:
            print(json.dumps(data[:3], indent=4, ensure_ascii=False))
        else:
            print("Транзакции не найдены (возможно, не подошли настройки парсера таблицы).")
    else:
        # Если пришел словарь с ошибкой
        print("ОШИБКА:", data)