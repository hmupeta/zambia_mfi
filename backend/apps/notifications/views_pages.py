from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def notifications_list(request):
    return render(request, 'app/notifications/list.html')


@never_cache
def notifications_templates(request):
    return render(request, 'app/notifications/templates.html')


@never_cache
def notifications_settings(request):
    return render(request, 'app/notifications/settings.html')
