import pdfplumber
import re
import os
import json
from decimal import Decimal
from google import genai
from google.genai import types


# Вспомогательная функция очистки суммы
def clean_amount(amount_str):
    if not amount_str:
        return Decimal(0)
    # Удаляем пробелы, неразрывные пробелы (\xa0), валюту и переносы
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
                col_desc = " ".join(clean_row[2].split())
                col_amount = clean_row[3]

                # Фильтры заголовков
                if "Дата" in col_date or "Всего" in col_date or not re.search(r'\d{2}\.\d{2}\.\d{4}', col_date):
                    continue

                amount = clean_amount(col_amount)
                if amount == 0: continue

                t_type = "expense" if amount < 0 else "income"

                transactions.append({
                    "date": col_date.split()[0],  # 02.12.2025
                    "merchant": col_desc.strip(),
                    "amount": float(abs(amount)),
                    "currency": clean_row[4].replace("\n", ""),
                    "type": t_type,
                    "bank": "Halyk Bank"
                })
    return transactions


def parse_kaspi_gold(pdf):
    transactions = []
    # Регулярка под Kaspi (Дата - Знак - Сумма - Валюта - Описание)
    kaspi_pattern = re.compile(r'^(\d{2}\.\d{2}\.\d{2})\s+([-+])\s+([\d\s]+,\d{2})\s+₸\s+(.*)')

    for page in pdf.pages:
        text = page.extract_text()
        if not text: continue

        lines = text.split('\n')
        for line in lines:
            match = kaspi_pattern.search(line)
            if match:
                date_str = match.group(1)  # 07.02.26
                sign = match.group(2)  # -
                amount_str = match.group(3)  # 1 521,00
                description_raw = match.group(4).strip()

                # Дата: 07.02.26 -> 07.02.2026 (для совместимости)
                day, month, year_short = date_str.split('.')
                full_date = f"{day}.{month}.20{year_short}"

                amount = clean_amount(amount_str)
                t_type = "expense" if sign == '-' else "income"

                # Попытка отделить тип операции от магазина
                parts = re.split(r'\s{2,}', description_raw, maxsplit=1)
                if len(parts) > 1:
                    merchant = f"{parts[0]}: {parts[1]}"
                else:
                    merchant = description_raw

                if "Сумма заблокирована" in line: continue

                transactions.append({
                    "date": full_date,
                    "merchant": merchant,
                    "amount": float(amount),
                    "currency": "KZT",
                    "type": t_type,
                    "bank": "Kaspi Gold"
                })
    return transactions


def parse_receipt_image(image_path):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return {"error": "GEMINI_API_KEY не настроен"}
        
    try:
        client = genai.Client()
        
        prompt = """
        Проанализируй этот чек. Верни строго JSON в таком формате:
        {
          "merchant": "Название магазина (если не найдено, 'Неизвестно')",
          "date": "DD.MM.YYYY (если не найдено, текущая дата или null)",
          "amount": 1500.00 (общая сумма цифрой),
          "currency": "KZT",
          "type": "expense",
          "items":[
            {"name": "Молоко", "price": 500.00, "quantity": 1},
            {"name": "Хлеб", "price": 1000.00, "quantity": 1}
          ]
        }
        Не добавляй Markdown-разметку (как ```json) в ответ, верни только сырой JSON. Если это не чек или текст не читаем, верни {"error": "Не удалось распознать чек"}. Валюта по умолчанию KZT, тип по умолчанию "expense". Названия товаров переведи в нормальный читаемый вид.
        """
        
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt
            ],
            config=types.GenerateContentConfig(
                 response_mime_type="application/json",
            )
        )
        
        # Parse JSON
        text = response.text.strip()
        data = json.loads(text)
        
        if "error" in data:
            return data
            
        # Return as list of transactions
        return [data]
        
    except Exception as e:
        return {"error": f"Ошибка AI распознавания: {str(e)}"}


def extract_finance_data(file_path):
    if not os.path.exists(file_path):
        return {"error": "Файл не найден"}

    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png']:
        return parse_receipt_image(file_path)

    results = []
    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0: return {"error": "PDF пустой"}

            first_page_text = pdf.pages[0].extract_text()

            if 'Народный Банк' in first_page_text or 'Halyk' in first_page_text or 'HSBK' in first_page_text:
                results = parse_halyk_bank(pdf)
            elif 'Kaspi' in first_page_text:
                results = parse_kaspi_gold(pdf)
            else:
                return {"error": "Банк не распознан (поддерживаются Halyk и Kaspi)"}

    except Exception as e:
        return {"error": f"Ошибка парсинга: {str(e)}"}

    return results