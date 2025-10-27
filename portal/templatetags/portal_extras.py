from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get a value from a dictionary by key,
    returning None if not found.
    """
    return dictionary.get(key)


@register.filter
def as_currency(value):
    """
    Template filter to format a number as currency.
    """
    try:
        amount = float(value)
        return f"${amount:,.0f}"
    except (TypeError, ValueError):
        return ""
