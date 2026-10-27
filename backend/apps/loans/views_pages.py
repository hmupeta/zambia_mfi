# apps/loans/views_pages.py
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def groups_list(request):
    return render(request, 'app/groups/list.html')


@never_cache
def group_detail(request, pk):
    return render(request, 'app/groups/detail.html', {'group_id': str(pk)})

@never_cache
def loan_restructure(request, pk):
    return render(request, 'app/loans/restructure.html', {'loan_id': str(pk)})