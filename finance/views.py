from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractYear
import csv
from datetime import date, datetime
from django.views.decorators.http import require_POST
from django.http import JsonResponse
import json
import os
from .models import Transaction, ReceiptItem
from .ai_service import extract_finance_data, get_genai_client


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'finance/register.html', {'form': form})


def get_category_chip(t):
    """Возвращает CSS-класс чипа и его текст на основе поля category."""
    mapping = {
        'food': ('chip--food', '🍔 Еда'),
        'transport': ('chip--transport', '🚌 Транспорт'),
        'shopping': ('chip--shop', '🛍 Покупки'),
        'health': ('chip--health', '💊 Здоровье'),
        'entertainment': ('chip--entertainment', '🎭 Развлечения'),
        'salary': ('chip--salary', '💼 Зарплата'),
        'utilities': ('chip--utilities', '🧾 Коммунальные'),
        'other': ('chip--other', '📦 Другое'),
    }
    return mapping.get(t.category, ('chip--other', '📦 Другое'))


def auto_categorize(merchant, transaction_type):
    """Автоматически определяет категорию по описанию."""
    m = merchant.lower()
    if transaction_type == 'income':
        return 'salary'
    
    if any(kw in m for kw in ('кофе', 'food', 'еда', 'cafe', 'ресторан', 'burger', 'pizza', 'суши', 'донер')):
        return 'food'
    if any(kw in m for kw in ('такси', 'uber', 'транспорт', 'yandex', 'автобус', 'metro', 'бензин', 'gas')):
        return 'transport'
    if any(kw in m for kw in ('аптека', 'health', 'медицин', 'клиника', 'больница', 'стоматолог')):
        return 'health'
    if any(kw in m for kw in ('каспи', 'kaspi', 'магазин', 'market', 'shop', 'mall', 'store', 'wb', 'wildberries', 'ozon')):
        return 'shopping'
    if any(kw in m for kw in ('кино', 'cinema', 'парк', 'игровой', 'game', 'play', 'подписка')):
        return 'entertainment'
    if any(kw in m for kw in ('коммунал', 'свет', 'вода', 'газ', 'отопление', 'кск', 'оплата услуг')):
        return 'utilities'
    
    return 'other'


RU_MONTHS = [
    (1, 'Январь'),
    (2, 'Февраль'),
    (3, 'Март'),
    (4, 'Апрель'),
    (5, 'Май'),
    (6, 'Июнь'),
    (7, 'Июль'),
    (8, 'Август'),
    (9, 'Сентябрь'),
    (10, 'Октябрь'),
    (11, 'Ноябрь'),
    (12, 'Декабрь'),
]
RU_MONTH_DICT = dict(RU_MONTHS)


def get_month_display(month, year):
    return f"{RU_MONTH_DICT.get(month, '')} {year}"


def get_calendar_context(month, year):
    today = date.today()
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    current_actual_year = today.year
    available_years = list(range(current_actual_year - 4, current_actual_year + 3))
    if year not in available_years:
        available_years.append(year)
        available_years.sort()

    return {
        'current_month': month,
        'current_year': year,
        'today_month': today.month,
        'today_year': today.year,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'month_display': get_month_display(month, year),
        'month_input_val': f"{year:04d}-{month:02d}",
        'all_months': RU_MONTHS,
        'available_years': available_years,
    }


@login_required
def dashboard(request):
    # 1. Month/Year filtering logic
    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    cal_ctx = get_calendar_context(month, year)

    # 2. Base transactions for current user
    user_transactions = Transaction.objects.filter(user=request.user)
    
    # 3. Totals (Global)
    income_total = user_transactions.filter(transaction_type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    expense_total = user_transactions.filter(transaction_type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    balance = income_total - expense_total

    # 4. Monthly breakdowns for chart
    monthly_expenses = user_transactions.filter(
        transaction_type='expense',
        date__month=month,
        date__year=year
    )

    category_data = monthly_expenses.values('category').annotate(total=Sum('amount'))
    
    chart_labels = []
    chart_values = []
    chart_colors = {
        'food': '#FF6384',
        'transport': '#36A2EB',
        'shopping': '#FFCE56',
        'health': '#4BC0C0',
        'entertainment': '#9966FF',
        'salary': '#4CAF50',
        'utilities': '#FF9F40',
        'other': '#C9CBCF'
    }
    chart_bg_colors = []
    
    mapping = {
        'food': 'Еда',
        'transport': 'Транспорт',
        'shopping': 'Покупки',
        'health': 'Здоровье',
        'entertainment': 'Развлечения',
        'salary': 'Зарплата',
        'utilities': 'Услуги',
        'other': 'Другое'
    }

    for item in category_data:
        cat = item['category']
        chart_labels.append(mapping.get(cat, 'Другое'))
        chart_values.append(float(item['total']))
        chart_bg_colors.append(chart_colors.get(cat, '#C9CBCF'))

    # 5. Transactions for table (maybe filtered by month too? Usually better)
    category = request.GET.get('category', 'all')
    table_transactions_qs = user_transactions.filter(
        date__month=month,
        date__year=year
    )
    
    if category != 'all':
        table_transactions_qs = table_transactions_qs.filter(category=category)
        
    table_transactions = list(table_transactions_qs.order_by('-date', '-created_at'))
    for t in table_transactions:
        t.chip_class, t.chip_label = get_category_chip(t)

    context = {
        'transactions': table_transactions,
        'balance': balance,
        'income': income_total,
        'expense': expense_total,
        # Chart Data
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'chart_bg_colors': chart_bg_colors,
        'categories': Transaction.CATEGORY_CHOICES,
        'current_category': category,
        **cal_ctx
    }
    return render(request, 'finance/dashboard.html', context)


@login_required
def all_transactions(request):
    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    category = request.GET.get('category', 'all')
    cal_ctx = get_calendar_context(month, year)

    transactions_qs = Transaction.objects.filter(
        user=request.user,
        date__month=month,
        date__year=year
    )

    if category != 'all':
        transactions_qs = transactions_qs.filter(category=category)

    transactions = transactions_qs.order_by('-date', '-created_at')
    
    for t in transactions:
        t.chip_class, t.chip_label = get_category_chip(t)

    context = {
        'transactions': transactions,
        'categories': Transaction.CATEGORY_CHOICES,
        'current_category': category,
        **cal_ctx
    }
    return render(request, 'finance/transactions.html', context)


@login_required
def upload_file(request):
    if request.method == 'POST' and request.FILES.get('document'):
        uploaded_file = request.FILES['document']
        fs = FileSystemStorage()
        filename = fs.save(uploaded_file.name, uploaded_file)
        file_path = fs.path(filename)

        data = extract_finance_data(file_path)

        if isinstance(data, list):
            for item in data:
                try:
                    date_obj = datetime.strptime(item['date'], "%d.%m.%Y").date()
                except (ValueError, TypeError):
                    date_obj = None

                t = Transaction.objects.create(
                    user=request.user,
                    date=date_obj,
                    merchant=item['merchant'],
                    amount=item['amount'],
                    currency=item['currency'],
                    transaction_type=item['type'],
                    category=auto_categorize(item['merchant'], item['type']),
                    source_file=filename
                )
                
                # Check for parsed items from receipt and save them
                if "items" in item and isinstance(item["items"], list):
                    for r_item in item["items"]:
                        ReceiptItem.objects.create(
                            transaction=t,
                            name=r_item.get("name", "Неизвестно"),
                            price=r_item.get("price", 0),
                            quantity=r_item.get("quantity", 1)
                        )

            return redirect('dashboard')
        else:
            error_msg = data.get('error', 'Неизвестная ошибка')
            return render(request, 'finance/upload.html', {'error': error_msg})

    return render(request, 'finance/upload.html')


@login_required
@require_POST
def export_transactions(request):
    selected_ids = request.POST.getlist('transaction_ids')
    if not selected_ids:
        return redirect('dashboard')

    response = HttpResponse(content_type='text/csv')
    response.write(u'\ufeff'.encode('utf8'))
    response['Content-Disposition'] = 'attachment; filename="selected_finances.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Дата', 'Описание', 'Сумма', 'Валюта', 'Тип', 'Категория'])

    transactions = Transaction.objects.filter(user=request.user, id__in=selected_ids).order_by('-date')

    for t in transactions:
        writer.writerow([
            t.date.strftime("%d.%m.%Y") if t.date else "",
            t.merchant,
            t.amount,
            t.currency,
            t.get_transaction_type_display(),
            t.get_category_display()
        ])

    return response


@login_required
@require_POST
def edit_receipt_item(request, item_id):
    try:
        item = ReceiptItem.objects.get(id=item_id, transaction__user=request.user)
        data = json.loads(request.body)
        
        item.name = data.get('name', item.name)
        item.price = data.get('price', item.price)
        item.quantity = data.get('quantity', item.quantity)
        
        item.save()
        return JsonResponse({"status": "success"})
    except ReceiptItem.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Товар не найден"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def get_ai_advice(request):
    today = date.today()
    expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__month=today.month,
        date__year=today.year
    ).values('category').annotate(total=Sum('amount'))
    
    mapping = {
        'food': 'Еда',
        'transport': 'Транспорт',
        'shopping': 'Покупки',
        'health': 'Здоровье',
        'entertainment': 'Развлечения',
        'salary': 'Зарплата',
        'utilities': 'Услуги',
        'other': 'Другое'
    }
    
    summary_lines = []
    for exp in expenses:
        cat_name = mapping.get(exp['category'], 'Другое')
        total = exp['total']
        summary_lines.append(f"{cat_name}: {total} тг")
        
    summary_text = ", ".join(summary_lines)
    if not summary_text:
        return JsonResponse({"advice": "Пока нет данных о тратах в этом месяце. Начните добавлять расходы!"})
        
    prompt = f"Проанализируй эти траты пользователя по категориям за текущий месяц и дай 1 короткий, полезный и подбадривающий финансовый совет на русском языке. Только текст совета, без markdown.\n{summary_text}"
    
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return JsonResponse({"advice": "GEMINI_API_KEY не установлен. Пожалуйста, добавьте ключ в переменные окружения."})
        
    try:
        client = get_genai_client()
        use_vertex = os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', 'true').lower() in ('true', '1', 'yes')
        model_name = 'gemini-2.5-flash' if use_vertex else 'gemini-3.8-flash'
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return JsonResponse({"advice": response.text.strip()})
    except Exception as e:
        return JsonResponse({"advice": f"Не удалось получить совет от ИИ: {e}"})


@login_required
def ai_chatbot_page(request):
    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))
    cal_ctx = get_calendar_context(month, year)
    return render(request, 'finance/chatbot.html', cal_ctx)


@login_required
@require_POST
def api_chat_message(request):
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        month = int(data.get('month', date.today().month))
        year = int(data.get('year', date.today().year))
        history = data.get('history', [])

        # Limit history to last 6 messages to save tokens
        history = history[-6:]
        
        # Get user's expenses for that month
        expenses = Transaction.objects.filter(
            user=request.user,
            transaction_type='expense',
            date__month=month,
            date__year=year
        ).values('category').annotate(total=Sum('amount'))
        
        mapping = {
            'food': 'Еда',
            'transport': 'Транспорт',
            'shopping': 'Покупки',
            'health': 'Здоровье',
            'entertainment': 'Развлечения',
            'salary': 'Зарплата',
            'utilities': 'Услуги',
            'other': 'Другое'
        }
        
        summary_lines = []
        for exp in expenses:
            cat_name = mapping.get(exp['category'], 'Другое')
            summary_lines.append(f"- {cat_name}: {exp['total']} тг")
            
        summary_text = "\n".join(summary_lines)
        if not summary_text:
            summary_text = "Нет данных о расходах."

        prompt = f"Ты умный и полезный финансовый помощник Baqlau AI. Твоя задача — помогать пользователю анализировать его траты и давать советы. Отвечай кратко, дружелюбно и по делу.\n\nДанные пользователя по расходам за выбранный месяц:\n{summary_text}\n\n"
        
        if history:
            prompt += "История недавнего диалога:\n"
            for msg in history:
                role = "Пользователь" if msg.get("role") == "user" else "Baqlau AI"
                prompt += f"{role}: {msg.get('text')}\n"
        
        prompt += f"\nПользователь сейчас: {user_message}\nBaqlau AI:"
        
        client = get_genai_client()
        use_vertex = os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', 'true').lower() in ('true', '1', 'yes')
        model_name = 'gemini-2.5-flash' if use_vertex else 'gemini-3.8-flash'
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return JsonResponse({"response": response.text.strip()})
    except Exception as e:
        return JsonResponse({"error": f"Ошибка AI сервиса: {str(e)}"}, status=500)
