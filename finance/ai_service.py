import os
import json
import google.generativeai as genai
from django.conf import settings
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def parse_finance_document(file_path, mime_type):
    """
    Отправляет файл в Gemini и возвращает чистый JSON.
    """
    model = genai.GenerativeModel("gemini-2.0-flash")

    # Промпт адаптирован для KZT/RUB и точной структуры
    prompt = """
    Ты профессиональный бухгалтер. Проанализируй этот документ (чек или выписку).

    Твоя задача вернуть JSON строго следующей структуры:
    {
        "merchant": "Название магазина или описание транзакции",
        "date": "YYYY-MM-DD" (если даты нет, поставь сегодняшнюю),
        "total_amount": число (float),
        "currency": "KZT" (или RUB/USD, определи по символу),
        "items": [
            {"name": "Название товара", "price": цена_за_единицу, "quantity": кол-во, "category": "Категория товара"}
        ]
    }

    Если это выписка с кучей транзакций, возьми только ПЕРВУЮ или самую крупную (для упрощения пока что), 
    или если это один чек - верни его детали.
    Верни ТОЛЬКО JSON без markdown оформления.
    """

    # Подготовка файла для отправки
    with open(file_path, "rb") as f:
        file_data = f.read()

    try:
        content = [
            {"mime_type": mime_type, "data": file_data},
            prompt
        ]

        response = model.generate_content(content)
        text = response.text.strip()

        # Очистка от ```json ... ```
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text)

    except Exception as e:
        print(f"Ошибка AI: {e}")
        return None