import re
from django import template
from django.utils.html import linebreaks
from django.utils.safestring import mark_safe

from apps.core.models import NavItem

register = template.Library()


# ------------------------------------------------------------
# Markdown rendering
# ------------------------------------------------------------
try:
    import markdown as md_lib

    def _render_markdown(text):
        html = md_lib.markdown(
            text or '',
            extensions=['extra', 'nl2br', 'sane_lists'],
        )
        return mark_safe(html)
except ImportError:
    def _render_markdown(text):
        return mark_safe(linebreaks(text or ''))


@register.filter
def markdownify(text):
    return _render_markdown(text)


# ------------------------------------------------------------
# Block renderer — dispatches to the right partial
# ------------------------------------------------------------
@register.simple_tag(takes_context=True)
def render_block(context, block):
    tpl = template.loader.get_template(f'partials/blocks/{block.block_type}.html')
    return tpl.render({'block': block}, request=context.get('request'))


# ------------------------------------------------------------
# Navigation renderer
# ------------------------------------------------------------
@register.simple_tag(takes_context=True)
def nav_menu(context, menu_name):
    items = NavItem.objects.filter(menu=menu_name, is_visible=True).select_related('page')
    return items


# ------------------------------------------------------------
# Simple helpers
# ------------------------------------------------------------
@register.filter
def comma_split(value):
    return [v.strip() for v in (value or '').split(',') if v.strip()]