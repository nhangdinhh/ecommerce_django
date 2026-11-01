from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from core.models import Category

register = template.Library()


@register.simple_tag
def categories():
    items = Category.objects.filter(is_active=True).order_by('title')
    items_li = ""
    for i in items:
        items_li += """<li><a href="/category/{}">{}</a></li>""".format(i.slug, i.title)
    return mark_safe(items_li)

@register.simple_tag
def categories_mobile():
    items = Category.objects.filter(is_active=True).order_by('title')
    items_li = ""
    for i in items:
        items_li += """<li class="item-menu-mobile"><a href="/category/{}">{}</a></li>""".format(i.slug, i.title)
    return mark_safe(items_li)


@register.simple_tag
def categories_li_a():
    items = Category.objects.filter(is_active=True).order_by('title')
    items_li_a = ""
    for i in items:
        items_li_a += """<li class="p-t-4"><a href="/category/{}" class="s-text13">{}</a></li>""".format(i.slug,
                                                                                                         i.title)
    return mark_safe(items_li_a)


@register.simple_tag
def categories_div():
    """
    section banner
    :return:
    """
    items = list(Category.objects.filter(is_active=True).order_by('title'))
    columns = []
    for start in range(0, len(items), 2):
        cards = items[start:start + 2]
        card_html = format_html_join(
            '',
            '<div class="block1 hov-img-zoom pos-relative m-b-30">{}'
            '<div class="block1-wrapbtn w-size2"><a href="{}" '
            'class="flex-c-m size2 m-text2 bg3 hov1 trans-0-4">{}</a></div></div>',
            (
                (
                    format_html(
                        '<img src="{}" alt="{}" loading="lazy">',
                        category.image.url,
                        category.title,
                    ) if category.image else '',
                    category.get_absolute_url(),
                    category.title,
                )
                for category in cards
            ),
        )
        columns.append(format_html(
            '<div class="col-sm-10 col-md-8 col-lg-4 m-l-r-auto">{}</div>',
            card_html,
        ))

    return format_html_join('', '{}', ((column,) for column in columns))

from core.models import Item
@register.inclusion_tag('featured_sidebar.html')
def featured_sidebar_items():
    items = Item.objects.filter(is_active=True).order_by('-id')[:3]
    return {'items': items}
