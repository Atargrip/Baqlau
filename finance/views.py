from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse  # Для экспорта
import csv  # Для экспорта
from datetime import datetime  # Для конвертации даты
from django.views.decorators.http import require_POST
from .models import Transaction
from .ai_service import extract_finance_data


def get_category_chip(t):
    """Возвращает CSS-класс чипа и его текст по типу/мерчанту транзакции."""
    if t.transaction_type == 'income':
        return 'chip--salary', '💼 Зарплата'
    m = t.merchant.lower()
    if any(kw in m for kw in ('кофе', 'food', 'еда', 'cafe', 'ресторан', 'burger', 'pizza', 'суши')):
        return 'chip--food', '🍔 Еда'
    if any(kw in m for kw in ('аптека', 'health', 'медицин', 'клиника', 'больниц')):
        return 'chip--health', '💊 Здоровье'
    if any(kw in m for kw in ('каспи', 'kaspi', 'магазин', 'market', 'shop', 'mall', 'store')):
        return 'chip--shop', '🛍 Покупки'
    if any(kw in m for kw in ('такси', 'uber', 'транспорт', 'yandex', 'автобус', 'metro')):
        return 'chip--transport', '🚌 Транспорт'
    return 'chip--other', '📦 Другое'


def dashboard(request):
    transactions = list(Transaction.objects.all().order_by('-date', '-created_at'))

    # Считаем баланс
    income = sum(t.amount for t in transactions if t.transaction_type == 'income')
    expense = sum(t.amount for t in transactions if t.transaction_type == 'expense')
    balance = income - expense

    # Аннотируем каждую транзакцию данными чипа (без изменения модели)
    for t in transactions:
        t.chip_class, t.chip_label = get_category_chip(t)

    context = {
        'transactions': transactions,
        'balance': balance,
        'income': income,
        'expense': expense
    }
    return render(request, 'finance/dashboard.html', context)


def upload_file(request):
    if request.method == 'POST' and request.FILES.get('document'):
        uploaded_file = request.FILES['document']

        # 1. Сохраняем файл временно
        fs = FileSystemStorage()
        filename = fs.save(uploaded_file.name, uploaded_file)
        file_path = fs.path(filename)

        # 2. Парсим
        data = extract_finance_data(file_path)

        # 3. Обрабатываем результат
        if isinstance(data, list):
            for item in data:
                # Конвертируем дату из строки "DD.MM.YYYY" в формат Python Date
                try:
                    date_obj = datetime.strptime(item['date'], "%d.%m.%Y").date()
                except ValueError:
                    date_obj = None  # Или ставим сегодня

                # Создаем запись в БД
                Transaction.objects.create(
                    date=date_obj,
                    merchant=item['merchant'],
                    amount=item['amount'],
                    currency=item['currency'],
                    transaction_type=item['type'],
                    source_file=filename  # Ссылка на загруженный файл
                )
            return redirect('dashboard')
        else:
            # Если пришла ошибка (словарь)
            error_msg = data.get('error', 'Неизвестная ошибка')
            return render(request, 'finance/upload.html', {'error': error_msg})

    return render(request, 'finance/upload.html')




@require_POST  # Разрешаем только POST запрос для безопасности (передача списка ID)
def export_transactions(request):
    # Получаем список ID из формы
    selected_ids = request.POST.getlist('transaction_ids')

    if not selected_ids:
        return redirect('dashboard')

    # Создаем CSV ответ
    response = HttpResponse(content_type='text/csv')
    response.write(u'\ufeff'.encode('utf8'))  # Исправляет кодировку для Excel (чтобы русский текст читался)
    response['Content-Disposition'] = 'attachment; filename="selected_finances.csv"'

    writer = csv.writer(response, delimiter=';')  # Точка с запятой лучше для Excel в СНГ
    writer.writerow(['Дата', 'Описание', 'Сумма', 'Валюта', 'Тип'])

    # Фильтруем транзакции: берем только те, чьи ID есть в списке selected_ids
    transactions = Transaction.objects.filter(id__in=selected_ids).order_by('-date')

    for t in transactions:
        writer.writerow([
            t.date.strftime("%d.%m.%Y") if t.date else "",
            t.merchant,
            t.amount,
            t.currency,
            t.get_transaction_type_display()
        ])

    return response
