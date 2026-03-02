from django.db import models
from django.contrib.auth.models import User


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('income', 'Доход'),
        ('expense', 'Расход'),
    ]

    CATEGORY_CHOICES = [
        ('food', '🍔 Еда'),
        ('transport', '🚌 Транспорт'),
        ('shopping', '🛍 Покупки'),
        ('health', '💊 Здоровье'),
        ('entertainment', '🎭 Развлечения'),
        ('salary', '💼 Зарплата'),
        ('utilities', '🧾 Коммунальные'),
        ('other', '📦 Другое'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField(null=True, blank=True, verbose_name="Дата")
    merchant = models.CharField(max_length=255, default="Неизвестно", verbose_name="Магазин/Описание")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    currency = models.CharField(max_length=10, default="KZT", verbose_name="Валюта")
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='expense')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name="Категория")

    source_file = models.FileField(upload_to='uploads/%Y/%m/', verbose_name="Исходный файл", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | {self.date} | {self.merchant} | {self.amount}"


class ReceiptItem(models.Model):
    """Детали чека (если удалось распознать позиции)"""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.FloatField(default=1.0)
    category = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
