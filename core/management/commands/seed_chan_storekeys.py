from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import Profile, StoreKey

class Command(BaseCommand):
    help = "Seed demo store keys for user 'chan' with phone and created_at so they appear on dashboard."

    def handle(self, *args, **options):
        # 1) Create or get user 'chan'
        user, created = User.objects.get_or_create(username='chan', defaults={"is_active": True})
        if created:
            self.stdout.write(self.style.SUCCESS("Created user 'chan'"))
        else:
            self.stdout.write("User 'chan' already exists")

        # 2) Ensure Profile with phone exists
        profile, p_created = Profile.objects.get_or_create(user=user, defaults={"phone": "13800138000"})
        if not p_created and not (profile.phone or '').strip():
            profile.phone = "13800138000"
            profile.save()
            self.stdout.write("Updated 'chan' phone to 13800138000")
        else:
            self.stdout.write("Profile for 'chan' ready (phone: %s)" % profile.phone)

        # 3) Seed several StoreKey entries
        seeds = [
            ("CN001", "sk_cn_9d7f54b2"),
            ("US002", "sk_us_3a8c12f7"),
            ("EU003", "sk_eu_7c4b91de"),
        ]
        created_count = 0
        for code, secret in seeds:
            obj, ok = StoreKey.objects.get_or_create(user=user, store_code=code, defaults={"secret": secret})
            if ok:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created_count} store keys for 'chan'"))

        self.stdout.write(self.style.SUCCESS("Done."))