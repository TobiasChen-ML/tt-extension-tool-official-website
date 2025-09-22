from django.contrib import admin
from .models import Profile, Product, Order, SensitiveWord, BrandWord, ForbiddenWord, KeywordEntry, UserInfo, Category, Word, WordAlias, WordLog

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "monthly_quota", "quota_used")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_no", "user", "amount", "status", "created_at")

@admin.register(SensitiveWord)
class SensitiveWordAdmin(admin.ModelAdmin):
    list_display = ("word", "level1", "level2", "level3", "created_at")
    search_fields = ("word", "level1", "level2", "level3")
    list_filter = ("level1", "level2", "level3")

@admin.register(BrandWord)
class BrandWordAdmin(admin.ModelAdmin):
    list_display = ("word", "category", "created_at")
    search_fields = ("word", "category")
    list_filter = ("category",)

@admin.register(ForbiddenWord)
class ForbiddenWordAdmin(admin.ModelAdmin):
    list_display = ("word", "level1", "level2", "level3", "created_at")
    search_fields = ("word", "level1", "level2", "level3")
    list_filter = ("level1", "level2", "level3")

@admin.register(KeywordEntry)
class KeywordEntryAdmin(admin.ModelAdmin):
    list_display = ("word", "level1", "level2", "level3", "created_at")
    search_fields = ("word", "level1", "level2", "level3")
    list_filter = ("level1", "level2", "level3")

@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    list_display = ("phone", "permission", "expire_at", "store_count", "created_at")
    search_fields = ("phone", "permission")
    list_filter = ("permission",)

# 新增：标准化词库 Admin
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_at", "updated_at")
    search_fields = ("name",)

@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("word", "category", "severity", "is_active", "created_at")
    search_fields = ("word",)
    list_filter = ("severity", "is_active", "category")

@admin.register(WordAlias)
class WordAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "word")
    search_fields = ("alias", "word__word")
    list_filter = ("word",)

@admin.register(WordLog)
class WordLogAdmin(admin.ModelAdmin):
    list_display = ("word", "context", "matched_at")
    search_fields = ("context", "word__word")
    list_filter = ("matched_at",)