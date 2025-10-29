# advertisement/admin.py
from django.contrib import admin
from traitkeeper.admin_site import admin_site
from traitkeeper.admin_utils import AdvancedFilterAdmin
from .models import  HeroSlide
from django.utils.html import format_html
from django.contrib import messages



@admin.register(HeroSlide, site=admin_site)
class HeroSlideAdmin(AdvancedFilterAdmin):
    list_display = ['title', 'is_active', 'display_url', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'button_text', 'button_url', 'image_url', 'url', 'is_active', 'created_at')
        }),
    )
    readonly_fields = ['created_at']
    change_list_template = "admin/change_list.html"

    def save_model(self, request, obj, form, change):
        # Ensure only one HeroSlide is active
        if obj.is_active:
            HeroSlide.objects.exclude(id=obj.id).update(is_active=False)
        super().save_model(request, obj, form, change)
        # If no slide is active, set this one as active
        if not HeroSlide.objects.filter(is_active=True).exists():
            obj.is_active = True
            obj.save()

    def display_url(self, obj):
        if obj.url:
            return format_html('<a href="{}" target="_blank">Visit</a>', obj.url)
        return "-"
    display_url.short_description = "URL"