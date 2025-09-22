from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_migrate
        from django.contrib.auth import get_user_model
        from django.db import connection

        def ensure_admin_user(sender=None, **kwargs):
            User = get_user_model()
            # 优先获取目标账号
            user = User.objects.filter(username='chengong').first()
            # 若不存在则尝试迁移旧的 admin 账号
            if not user:
                user = User.objects.filter(username='admin').first()
            if user:
                user.username = 'chengong'
                user.is_superuser = True
                user.is_staff = True
                user.set_password('chengong123')
                user.save()
            else:
                User.objects.create_superuser('chengong', email='', password='chengong123')

        def ensure_fts_table(sender=None, **kwargs):
            # 创建 FTS5 虚拟表（如不存在）
            try:
                with connection.cursor() as cursor:
                    cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS word_index USING fts5(word)")
            except Exception:
                # 若底层SQLite不支持FTS5或迁移阶段，忽略错误
                pass

        # 启动时确保账号和FTS表存在
        ensure_admin_user()
        ensure_fts_table()
        # 迁移完成后也确保账号和FTS表存在
        post_migrate.connect(ensure_admin_user, sender=self)
        post_migrate.connect(ensure_fts_table, sender=self)