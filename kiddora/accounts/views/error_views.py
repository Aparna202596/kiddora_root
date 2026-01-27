from django.shortcuts import render

def handler404(request, exception):
    return render(request, "accounts/errors/404.html", status=404)

def handler500(request):
    return render(request, "accounts/errors/500.html", status=500)

def handler403(request, exception):
    return render(request, "accounts/errors/403.html", status=403)

def blocked(request):
    return render(request, "accounts/errors/blocked.html")