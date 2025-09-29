from django.contrib import admin
from .models import Profile, Product, Order, UserInfo, Category, Word, WordAlias, WordLog, UsageLog, PointsBalance, Suggestion, Trial, StoreKey


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'monthly_quota')
    search_fields = ('user__username', 'phone')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')
    search_fields = ('name',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'user', 'amount', 'status', 'created_at')
    search_fields = ('order_no', 'user__username')
    list_filter = ('status',)


# 用户信息库
@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'permission', 'expire_at', 'store_count', 'created_at')
    search_fields = ('user__username', 'phone', 'permission')
    list_filter = ('permission',)


# 标准化词库
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ('word', 'category', 'severity', 'is_active', 'created_at')
    search_fields = ('word', 'category__name')
    list_filter = ('category', 'severity', 'is_active')


@admin.register(WordAlias)
class WordAliasAdmin(admin.ModelAdmin):
    list_display = ('word', 'alias')
    search_fields = ('alias', 'word__word')


@admin.register(WordLog)
class WordLogAdmin(admin.ModelAdmin):
    list_display = ('word', 'context', 'matched_at')
    search_fields = ('context', 'word__word')


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'content', 'store_code', 'points_consumed', 'status')
    search_fields = ('content', 'store_code')
    list_filter = ('status',)


@admin.register(PointsBalance)
class PointsBalanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'store_code', 'points')
    search_fields = ('user__username', 'store_code')


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('shop_code', 'phone', 'processed', 'created_at')
    search_fields = ('shop_code', 'phone', 'suggest')
    list_filter = ('processed',)


admin.site.register(Trial)


@admin.register(StoreKey)
class StoreKeyAdmin(admin.ModelAdmin):
    list_display = ('user', 'store_code', 'secret', 'created_at')
    search_fields = ('user__username', 'store_code')
    list_filter = ()