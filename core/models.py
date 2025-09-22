from django.db import models
from django.contrib.auth.models import User
import random
# 新增：用于FTS5索引同步
from django.db import connection
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

AVATAR_CHOICES = [
    '👾','🦊','🐼','🐯','🐶','🐱','🐸','🐨','🐵','🦄','🐧','🐰','🐹','🐻','🐷','🐙'
]

def random_avatar():
    return random.choice(AVATAR_CHOICES)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, unique=True)
    avatar = models.CharField(max_length=2, default=random_avatar)
    monthly_quota = models.IntegerField(default=300)
    quota_used = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username}"

class Product(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending','待支付'),
        ('paid','已支付'),
        ('failed','失败'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    order_no = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order_no} - {self.status}"

# 词库与用户信息库
class SensitiveWord(models.Model):
    level1 = models.CharField(max_length=100, blank=True, default='')
    level2 = models.CharField(max_length=100, blank=True, default='')
    level3 = models.CharField(max_length=100, blank=True, default='')
    word = models.CharField(max_length=200)
    remark = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['word']),
            models.Index(fields=['level1','level2','level3']),
        ]
        verbose_name = '敏感词'
        verbose_name_plural = '敏感词库'

    def __str__(self):
        return self.word

class BrandWord(models.Model):
    category = models.CharField(max_length=100, blank=True, default='')  # 一级分类
    word = models.CharField(max_length=200)
    remark = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['word']), models.Index(fields=['category'])]
        verbose_name = '品牌词'
        verbose_name_plural = '品牌词库'

    def __str__(self):
        return self.word

class ForbiddenWord(models.Model):
    level1 = models.CharField(max_length=100, blank=True, default='')
    level2 = models.CharField(max_length=100, blank=True, default='')
    level3 = models.CharField(max_length=100, blank=True, default='')
    word = models.CharField(max_length=200)
    remark = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['word']),
            models.Index(fields=['level1','level2','level3']),
        ]
        verbose_name = '违禁词'
        verbose_name_plural = '违禁词库'

    def __str__(self):
        return self.word

class KeywordEntry(models.Model):
    level1 = models.CharField(max_length=100, blank=True, default='')
    level2 = models.CharField(max_length=100, blank=True, default='')
    level3 = models.CharField(max_length=100, blank=True, default='')
    word = models.CharField(max_length=200)
    remark = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['word']),
            models.Index(fields=['level1','level2','level3']),
        ]
        verbose_name = '关键词'
        verbose_name_plural = '关键词库'

    def __str__(self):
        return self.word

class UserInfo(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True)
    permission = models.CharField(max_length=50, blank=True, default='')  # 权限标识/等级
    expire_at = models.DateTimeField(null=True, blank=True)
    store_count = models.IntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '用户信息'
        verbose_name_plural = '用户信息库'

    def __str__(self):
        return self.phone

# ---------------- 本地词库系统（标准化表） ----------------
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '词分类'
        verbose_name_plural = '词分类'

    def __str__(self):
        return self.name

class Word(models.Model):
    SEVERITY_CHOICES = (
        (1, '低'),
        (2, '中'),
        (3, '高'),
    )
    word = models.CharField(max_length=200, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='words')
    severity = models.PositiveSmallIntegerField(default=1, choices=SEVERITY_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['word'])]
        verbose_name = '词条'
        verbose_name_plural = '词条库'

    def __str__(self):
        return self.word

class WordAlias(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=200)

    class Meta:
        unique_together = ('word', 'alias')
        indexes = [models.Index(fields=['alias'])]
        verbose_name = '词别名'
        verbose_name_plural = '词别名'

    def __str__(self):
        return f"{self.alias} -> {self.word.word}"

class WordLog(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='logs')
    context = models.TextField(blank=True, default='')
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['matched_at'])]
        verbose_name = '词命中记录'
        verbose_name_plural = '词命中记录'

    def __str__(self):
        return f"{self.word.word} @ {self.matched_at.strftime('%Y-%m-%d %H:%M:%S')}"

# -------- FTS5 同步：保存/删除 Word 时更新全文索引 --------
@receiver(post_save, sender=Word)
def sync_word_to_fts(sender, instance: Word, **kwargs):
    try:
        with connection.cursor() as cursor:
            if instance.is_active:
                # 将 Word.id 作为 rowid，便于后续精确删除/更新
                cursor.execute("INSERT OR REPLACE INTO word_index(rowid, word) VALUES (?, ?)", [instance.id, instance.word])
            else:
                cursor.execute("DELETE FROM word_index WHERE rowid = ?", [instance.id])
    except Exception:
        # 在迁移或FTS表不存在时忽略错误
        pass

@receiver(post_delete, sender=Word)
def remove_word_from_fts(sender, instance: Word, **kwargs):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM word_index WHERE rowid = ?", [instance.id])
    except Exception:
        pass