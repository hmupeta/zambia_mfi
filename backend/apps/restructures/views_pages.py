# apps/restructures/views_pages.py
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def restructures_list(request):
    return render(request, 'app/restructures/list.html')


@never_cache
def restructure_detail(request, pk):
    return render(request, 'app/restructures/detail.html', {
        'restructure_id': str(pk),
    })