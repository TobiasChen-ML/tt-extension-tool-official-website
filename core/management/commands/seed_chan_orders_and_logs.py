from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import Profile, Product, Order, UsageLog, StoreKey
from decimal import Decimal
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = "Seed sample orders and usage logs for user 'chan'"

    def handle(self, *args, **options):
        user, _ = User.objects.get_or_create(username='chan')
        profile, _ = Profile.objects.get_or_create(user=user, defaults={'phone':'chan'})
        self.stdout.write("User 'chan' ready (phone: %s)" % profile.phone)

        # Ensure some products exist
        p1, _ = Product.objects.get_or_create(name='TK 灵犀-订阅A', defaults={'price': Decimal('99.00')})
        p2, _ = Product.objects.get_or_create(name='TK 灵犀-订阅B', defaults={'price': Decimal('199.00')})

        # Create Orders
        Order.objects.filter(user=user).delete()
        base_time = datetime.now() - timedelta(days=3)
        orders = [
            {'order_no':'CHAN-202509-001','amount':Decimal('99.00'),'status':'paid','product':p1,'created_at':base_time},
            {'order_no':'CHAN-202509-002','amount':Decimal('199.00'),'status':'paid','product':p2,'created_at':base_time+timedelta(hours=6)},
            {'order_no':'CHAN-202509-003','amount':Decimal('49.00'),'status':'paid','product':p1,'created_at':base_time+timedelta(days=1)},
        ]
        for o in orders:
            Order.objects.create(user=user, **o)
        self.stdout.write("Seeded %d orders for 'chan'" % len(orders))

        # Ensure store keys
        store_codes = list(StoreKey.objects.filter(user=user).values_list('store_code', flat=True))
        if not store_codes:
            store_codes = ['CN001','US002','EU003']

        # Create Usage Logs
        UsageLog.objects.filter(user=user).delete()
        logs = [
            {'content':'生成关键词','store_code':store_codes[0],'points_consumed':3,'status':'success'},
            {'content':'同义词扩展','store_code':store_codes[1],'points_consumed':2,'status':'success'},
            {'content':'文本清洗','store_code':store_codes[2],'points_consumed':5,'status':'success'},
        ]
        for i, l in enumerate(logs):
            ul = UsageLog.objects.create(user=user, **l)
            # spread times a bit (auto_now_add handles created_at)
        self.stdout.write("Seeded %d usage logs for 'chan'" % len(logs))

        self.stdout.write(self.style.SUCCESS('Done.'))