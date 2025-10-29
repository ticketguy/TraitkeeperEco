from django import template
from django.utils.html import format_html
from django.template.defaultfilters import stringfilter
from django.contrib.admin.templatetags.admin_list import (
    result_list as original_result_list,
    admin_list_filter as original_admin_list_filter,
    pagination as original_pagination,
    admin_actions as original_admin_actions,
)
from django.contrib.admin.templatetags.admin_modify import (
    submit_row as original_submit_row,
    prepopulated_fields_js as original_prepopulated_fields_js
)

register = template.Library()

# Re-registering admin template tags

@register.inclusion_tag("admin/change_list_results.html")
def result_list(cl):
    """Delegate to original result_list."""
    return {'cl': cl}

@register.inclusion_tag("admin/filter.html")
def admin_list_filter(cl, spec):
    """Delegate to original admin_list_filter."""
    return original_admin_list_filter(cl, spec)

@register.inclusion_tag("admin/pagination.html")
def pagination(cl):
    """Delegate to original pagination."""
    return original_pagination(cl)

@register.inclusion_tag("admin/actions.html", takes_context=True)
def admin_actions(context):
    """Delegate to original admin_actions."""
    return original_admin_actions(context)

@register.inclusion_tag("admin/submit_line.html", takes_context=True)
def submit_row(context):
    """Delegate to original submit_row."""
    return original_submit_row(context)

@register.inclusion_tag("admin/prepopulated_fields_js.html", takes_context=True)
def prepopulated_fields_js(context):
    """Delegate to original prepopulated_fields_js."""
    return original_prepopulated_fields_js(context)

# Custom filters

@register.filter
@stringfilter
def format_admin_field(value):
    """Format admin field values with proper styling"""
    if not value:
        return format_html('<span class="text-gray-500">-</span>')
    return value

@register.filter
def get_admin_field_display(obj, field_name):
    """Get the display value of a model field"""
    try:
        field = obj._meta.get_field(field_name)
        value = getattr(obj, field_name)
        if hasattr(field, 'choices') and field.choices:
            return dict(field.choices).get(value, value)
        return value
    except:
        return '-'

@register.simple_tag
def admin_boolean_icon(value):
    """Render a boolean value as an icon"""
    if value:
        return format_html('<i class="fas fa-check text-green-500"></i>')
    return format_html('<i class="fas fa-times text-red-500"></i>')

@register.filter
def admin_list_display_value(obj, field_name):
    """Get the display value for list_display fields"""
    try:
        if hasattr(obj, f'get_{field_name}_display'):
            return getattr(obj, f'get_{field_name}_display')()
        return getattr(obj, field_name)
    except:
        return '-'
    
@register.filter
def count_chars(value, char):
    """
    Count occurrences of a character in a string
    Usage: {{ my_string|count_chars:"a" }}
    """
    try:
        return value.count(str(char))
    except (AttributeError, TypeError):
        return 0