from django.shortcuts import render
from accounts.decorators import user_login_required,admin_login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
# request_return_view
# return_status_view
# @admin_login_required
# def admin_verify_return(request, return_id):
#     return_obj = Return.objects.get(id=return_id)
#     if return_obj.locked:
#         return redirect("returns:admin_list")

#     return_obj.status = "REFUNDED"
#     return_obj.locked = True
#     return_obj.save()
