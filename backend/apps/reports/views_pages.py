# apps/reports/views_pages.py
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def analytics_hub(request):
    return render(request, 'app/reports/analytics.html')

def reports_hub(request):
    return render(request, 'app/reports/hub.html')