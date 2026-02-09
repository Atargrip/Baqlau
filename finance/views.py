from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from .models import Transaction, ReceiptItem
from .ai_service import parse_finance_document
import mimetypes


def dashboard(request):
    # Получаем все транзакции из БД, от новых к старым
    transactions = Transaction.objects.all().order_by('-date', '-created_at')

    context = {
        'transactions': transactions
    }
    return render(request, 'dashboard.html', context)




def upload_file(request):
    if request.method == 'POST' and request.FILES['document']:
        uploaded_file = request.FILES['document']

        # 1. Сначала сохраняем файл физически через модель (временный объект)
        # Но проще сначала сохранить файл, чтобы получить путь для AI
        fs = FileSystemStorage()
        filename = fs.save(uploaded_file.name, uploaded_file)
        file_path = fs.path(filename)
        file_url = fs.url(filename)

        # Определяем MIME тип (pdf или image)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/pdf"  # fallback

        ai_data = parse_finance_document(file_path, mime_type)

        if ai_data:
            new_trans = Transaction.objects.create(
                date=ai_data.get('date'),
                merchant=ai_data.get('merchant', 'Unknown'),
                amount=ai_data.get('total_amount', 0),
                currency=ai_data.get('currency', 'KZT'),
                source_file=filename  # Привязываем файл
            )

            # Сохраняем товары, если есть
            items = ai_data.get('items', [])
            for item in items:
                ReceiptItem.objects.create(
                    transaction=new_trans,
                    name=item['name'],
                    price=item['price'],
                    quantity=item.get('quantity', 1),
                    category=item.get('category', '')
                )

        return redirect('dashboard')

    return render(request, 'finance/upload.html')