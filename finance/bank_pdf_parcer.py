import pdfplumber
import re
import os
import json
from decimal import Decimal


def clean_amount(amount_str):
    """Превращает строку '1 158,00' -> 1158.00"""
    if not amount_str:
        return Decimal(0)
    # Удаляем пробелы, неразрывные пробелы, валюту и переносы
    clean = str(amount_str).replace(" ", "").replace("\xa0", "").replace("\n", "").replace("₸", "")
    clean = clean.replace(",", ".")
    try:
        return Decimal(clean)
    except:
        return Decimal(0)


def parse_halyk_bank(pdf):
    transactions = []
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
                clean_row = [str(cell) if cell else "" for cell in row]
                if len(clean_row) < 4: continue

                col_date = clean_row[0].replace("\n", " ")
                col_desc = clean_row[2].replace("\n", " ")
                col_amount = clean_row[3]

                if "Дата" in col_date or "Всего" in col_date or not re.search(r'\d{2}\.\d{2}\.\d{4}', col_date):
                    continue

                amount = clean_amount(col_amount)
                if amount == 0: continue

                t_type = "expense" if amount < 0 else "income"

                transactions.append({
                    "date": col_date.split()[0],
                    "merchant": col_desc.strip(),
                    "amount": float(abs(amount)),
                    "currency": clean_row[4].replace("\n", ""),
                    "type": t_type,
                    "bank": "Halyk Bank"
                })
    return transactions


def parse_kaspi_gold(pdf):
    transactions = []

    kaspi_pattern = re.compile(r'^(\d{2}\.\d{2}\.\d{2})\s+([-+])\s+([\d\s]+,\d{2})\s+₸\s+(.*)')

    for page in pdf.pages:
        text = page.extract_text()
        if not text: continue

        lines = text.split('\n')

        for line in lines:
            match = kaspi_pattern.search(line)
            if match:
                date_str = match.group(1)  # 07.02.26
                sign = match.group(2)  # - или +
                amount_str = match.group(3)  # 1 521,00
                description_raw = match.group(4).strip()  # Покупка      Toimart

                # Приводим год к формату 2026
                day, month, year_short = date_str.split('.')
                full_date = f"{day}.{month}.20{year_short}"

                # Обработка суммы
                amount = clean_amount(amount_str)

                # Определение типа
                t_type = "expense" if sign == '-' else "income"

                # Разделение "Покупка" и "Магазин"
                # В Kaspi между ними обычно много пробелов, или просто склеены
                # Попробуем разделить по первому большому пробелу или просто возьмем все как описание
                parts = re.split(r'\s{2,}', description_raw, maxsplit=1)

                if len(parts) > 1:
                    operation_type = parts[0]  # Покупка / Перевод
                    merchant = parts[1]  # Toimart / На Kaspi Депозит
                else:
                    operation_type = "Операция"
                    merchant = description_raw

                # Игнорируем заблокированные суммы (внизу выписки)
                if "Сумма заблокирована" in line:
                    continue

                transactions.append({
                    "date": full_date,
                    "merchant": f"{operation_type}: {merchant}",  # Сохраняем тип в название для ясности
                    "amount": float(amount),
                    "currency": "KZT",
                    "type": t_type,
                    "bank": "Kaspi Gold"
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

            first_page_text = pdf.pages[0].extract_text()

            # Определение банка
            if 'Народный Банк' in first_page_text or 'Halyk' in first_page_text or 'HSBK' in first_page_text:
                print("✅ Банк определен: Halyk Bank")
                results = parse_halyk_bank(pdf)

            # Kaspi часто пишет "ВЫПИСКА по Kaspi Gold"
            elif 'Kaspi' in first_page_text:
                print("✅ Банк определен: Kaspi Gold")
                results = parse_kaspi_gold(pdf)

            else:
                return {"error": "Банк не распознан"}

    except Exception as e:
        return {"error": f"Ошибка при чтении PDF: {str(e)}"}

    return results


# --- ТЕСТ ---
if __name__ == "__main__":
    # Укажите путь к вашему файлу Kaspi
    file_name = "C:/Users/Aset/Desktop/gold_statement.pdf"

    data = extract_finance_data(file_name)

    if isinstance(data, list):
        print(f"Найдено транзакций: {len(data)}")
        if len(data) > 0:
            print(json.dumps(data[:5], indent=4, ensure_ascii=False))  # Покажем первые 5
    else:
        print("ОШИБКА:", data)