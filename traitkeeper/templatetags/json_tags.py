from django import template
import json

register = template.Library()

@register.filter
def json_encode(value):
    return json.dumps(value)