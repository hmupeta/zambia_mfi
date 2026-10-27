from django.http import Http404
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Page, BlogPost, ContactSubmission


# ============================================================
# Static pages (About, Contact, Terms...)
# ============================================================
def page_detail(request, slug):
    try:
        page = Page.objects.prefetch_related('blocks').get(slug=slug, is_published=True)
    except Page.DoesNotExist:
        raise Http404('Page not found')

    blocks = [b for b in page.blocks.all() if b.is_visible]

    template_map = {
        'default': 'pages/detail.html',
        'about': 'pages/about.html',
        'contact': 'pages/contact.html',
        'legal': 'pages/legal.html',
        'blank': 'pages/detail.html',
    }
    template = template_map.get(page.template, 'pages/detail.html')

    return render(request, template, {
        'page': page,
        'blocks': blocks,
        'site': __import__('apps.core.models', fromlist=['SiteSettings']).SiteSettings.load(),
    })


# ============================================================
# Blog
# ============================================================
def blog_list(request):
    posts = BlogPost.objects.filter(
        status='published',
        published_at__lte=timezone.now(),
    )

    category = request.GET.get('category')
    if category:
        posts = posts.filter(category=category)

    featured = posts.filter(is_featured=True).first()
    posts = posts.exclude(pk=featured.pk) if featured else posts

    return render(request, 'blog/list.html', {
        'featured': featured,
        'posts': posts,
        'site': __import__('apps.core.models', fromlist=['SiteSettings']).SiteSettings.load(),
    })


def blog_detail(request, slug):
    try:
        post = BlogPost.objects.get(slug=slug, status='published')
    except BlogPost.DoesNotExist:
        raise Http404

    BlogPost.objects.filter(pk=post.pk).update(views=post.views + 1)

    related = BlogPost.objects.filter(
        status='published',
    ).exclude(pk=post.pk)[:3]

    return render(request, 'blog/detail.html', {
        'post': post,
        'related': related,
        'site': __import__('apps.core.models', fromlist=['SiteSettings']).SiteSettings.load(),
    })


# ============================================================
# Contact form submission
# ============================================================
@require_POST
def contact_submit(request):
    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    message = request.POST.get('message', '').strip()

    if not (name and email and message):
        messages.error(request, 'Please fill in name, email, and message.')
        return redirect(request.META.get('HTTP_REFERER', '/'))

    ContactSubmission.objects.create(
        name=name,
        email=email,
        phone=request.POST.get('phone', '').strip(),
        company=request.POST.get('company', '').strip(),
        subject=request.POST.get('subject', '').strip(),
        message=message,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    messages.success(request, "Thanks! We'll be in touch shortly.")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def platform_documentation(request):
    return render(request, 'core/wiki.html')