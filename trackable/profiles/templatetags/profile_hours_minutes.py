from django import template
from trackable.core.utils import decimal_to_hours_and_minutes

register = template.Library()


@register.simple_tag
def split_hours_minutes(value):
    """Split decimal hours into a (hours, minutes) tuple."""
    hours, minutes = decimal_to_hours_and_minutes(value)
    return (hours, minutes)
