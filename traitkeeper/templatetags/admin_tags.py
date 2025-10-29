# traitkeeper/templatetags/admin_tags.py
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def lookup(obj, field):
    """
    Dynamically access a field or method on an object.
    If the field is a method, call it without arguments.
    Returns '-' if the field doesn't exist or an error occurs.
    """
    try:
        value = getattr(obj, field)
        if callable(value):
            value = value()
        return mark_safe(value) if value is not None else "-"
    except (AttributeError, TypeError):
        return "-"

@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary-like object (e.g., request.GET).
    """
    return dictionary.get(key, "")