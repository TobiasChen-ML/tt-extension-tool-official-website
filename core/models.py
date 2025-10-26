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
        ('paid','成功'),
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
# 删除：SensitiveWord、BrandWord、KeywordEntry 模型

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
        verbose_name = 'User Info'
        verbose_name_plural = 'User Info'

    def __str__(self):
        return self.phone

# ---------------- 新增：店铺密钥模型 ----------------
class StoreKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='store_keys')  # 账户
    store_code = models.CharField(max_length=100)  # 商店代号
    secret = models.CharField(max_length=255)  # 密钥（建议加密存储，当前为明文字段）
    created_at = models.DateTimeField(auto_now_add=True)  # 生成时间
    sales_person = models.CharField(max_length=100, blank=True, default='')  # 销售人员

    class Meta:
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['store_code']),
        ]
        unique_together = ('user', 'store_code')
        verbose_name = 'Store Key'
        verbose_name_plural = 'Store Keys'

    def __str__(self):
        return f"{self.user.username} - {self.store_code}"

# ---------------- 本地词库系统（标准化表） ----------------
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

class Word(models.Model):
    SEVERITY_CHOICES = (
        (1, 'low'),
        (2, 'medium'),
        (3, 'high'),
    )
    word = models.CharField(max_length=200, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='words')
    severity = models.PositiveSmallIntegerField(default=1, choices=SEVERITY_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['word'])]
        verbose_name = 'Word'
        verbose_name_plural = 'Words'

    def __str__(self):
        return self.word

class WordAlias(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=200)

    class Meta:
        unique_together = ('word', 'alias')
        indexes = [models.Index(fields=['alias'])]
        verbose_name = 'Word Alias'
        verbose_name_plural = 'Word Aliases'

    def __str__(self):
        return f"{self.alias} -> {self.word.word}"

class WordLog(models.Model):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='logs')
    context = models.TextField(blank=True, default='')
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['matched_at'])]
        verbose_name = 'Word Hit Log'
        verbose_name_plural = 'Word Hit Logs'

    def __str__(self):
        return f"{self.word.word} @ {self.matched_at.strftime('%Y-%m-%d %H:%M:%S')}"

# -------- FTS5 同步：保存/删除 Word 时更新全文索引 --------
@receiver(post_save, sender=Word)
def sync_word_to_fts(sender, instance: Word, **kwargs):
    try:
        with connection.cursor() as cursor:
            if instance.is_active:
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

# ---------------- 调用使用日志 ----------------
class UsageLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='usage_logs', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # 时间
    points_consumed = models.IntegerField(default=0)  # 消耗多少积分
    content = models.TextField(blank=True, default='')  # 接口（内容）
    store_code = models.CharField(max_length=100, blank=True, default='')  # 店铺代码
    status = models.CharField(max_length=10, choices=(('success','成功'),('failure','失败')), default='success')  # 状态

    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['store_code']),
        ]
        verbose_name = 'Usage Log'
        verbose_name_plural = 'Usage Logs'

    def __str__(self):
        return f"{self.created_at.strftime('%Y-%m-%d %H:%M:%S')} - {self.store_code} - {self.points_consumed} - {self.status}"

# ---------------- 新增：积分模型 ----------------
class PointsBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='points')
    store_code = models.CharField(max_length=100)
    points = models.PositiveIntegerField(default=0)  # 剩余积分

    class Meta:
        unique_together = ('user', 'store_code')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['store_code']),
        ]
        verbose_name = 'Points Balance'
        verbose_name_plural = 'Points Balances'

    def __str__(self):
        return f"{self.user.username} - {self.store_code}: {self.points}"

class Suggestion(models.Model):
    shop_code = models.CharField(max_length=100)
    suggest = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        db_table = 'suggestion'
        managed = True

    def __str__(self):
        return f"{self.shop_code} - {self.phone}"

class Trial(models.Model):
    shopcode = models.CharField(max_length=100, unique=True)
    times = models.IntegerField(default=0)

    class Meta:
        db_table = 'trials'
        indexes = [models.Index(fields=['shopcode'])]
        verbose_name = 'Trial'
        verbose_name_plural = 'Trials'

    def __str__(self):
        return f"{self.shopcode} - {self.times}"


class SalesInfo(models.Model):
    product_id = models.CharField(max_length=64)
    title = models.TextField(blank=True, default='')
    image_url = models.TextField(blank=True, default='')
    time_start = models.DateField(null=True, blank=True)
    time_end = models.DateField(null=True, blank=True)

    gross_sale = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    product_card_buyer_cnt = models.IntegerField(null=True, blank=True)
    product_card_ctr = models.FloatField(null=True, blank=True)
    product_card_cvr = models.FloatField(null=True, blank=True)
    product_card_gmv = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    product_card_listing_impression_cnt = models.IntegerField(null=True, blank=True)
    product_card_pv = models.IntegerField(null=True, blank=True)
    product_card_unit_sold_cnt = models.IntegerField(null=True, blank=True)
    product_card_uv = models.IntegerField(null=True, blank=True)
    unit_sold_cnt = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['product_id']),
            models.Index(fields=['time_start']),
            models.Index(fields=['time_end']),
        ]
        unique_together = ('product_id', 'time_start', 'time_end')
        verbose_name = 'Sales Info'
        verbose_name_plural = 'Sales Info'

    def __str__(self):
        return f"{self.product_id} - {self.time_start}~{self.time_end}"