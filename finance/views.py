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
from .models import Transaction
from .ai_service import extract_finance_data


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


@login_required
def dashboard(request):
    # 1. Month/Year filtering logic
    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    # Calculate prev/next month for buttons
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    selected_date = date(year, month, 1)
    month_name = selected_date.strftime("%B %Y") # We'll handle localization in template or just use format

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
    # Let's show all latest for now but we can filter if needed. The user didn't specify table filtering.
    table_transactions = list(user_transactions.order_by('-date', '-created_at'))
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
        # Month Controls
        'current_month': month,
        'current_year': year,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'month_display': month_name  # We can translate this in template
    }
    return render(request, 'finance/dashboard.html', context)


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

                Transaction.objects.create(
                    user=request.user,
                    date=date_obj,
                    merchant=item['merchant'],
                    amount=item['amount'],
                    currency=item['currency'],
                    transaction_type=item['type'],
                    category=auto_categorize(item['merchant'], item['type']),
                    source_file=filename
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

