from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def lookup(obj, attr):
    """
    Looks up an attribute of an object.
    Example usage: {{ my_obj|lookup:'attribute_name' }}
    """
    try:
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr)
    except (AttributeError, KeyError):
        return None