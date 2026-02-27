from django.views.decorators.cache import never_cache
from accounts.decorators import user_login_required
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from accounts.models import *
from django.contrib import messages

User = get_user_model()


@never_cache
@user_login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, "accounts/address/addresses.html", {"addresses": addresses})


@never_cache
@user_login_required
def set_default_address(request, address_id):
    UserAddress.objects.filter(user=request.user).update(is_default=False)
    address = get_object_or_404(UserAddress, id=address_id, user=request.user)
    address.is_default = True
    address.save()
    return redirect("accounts:address_list")


@never_cache
@user_login_required
def address_add(request):
    if request.method == "POST":
        form_data = request.POST.dict()
        address_line1 = request.POST.get("address_line1", "").strip()
        city          = request.POST.get("city", "").strip()
        state         = request.POST.get("state", "").strip()       
        country       = request.POST.get("country", "").strip()     
        pincode       = request.POST.get("pincode", "").strip()
        address_type  = request.POST.get("address_type", "").strip()

        if not all([address_line1, city, state, country, pincode]):
            messages.error(request, "All fields are required.")
            return render(request, "accounts/address/add_address.html", {"form_data": form_data})

        if not address_type:
            messages.error(request, "Address type is required.")
            return render(request, "accounts/address/add_address.html", {"form_data": form_data})

        is_default = request.POST.get("is_default") == "on"

        if is_default:
            UserAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)

        UserAddress.objects.create(
            user=request.user,
            address_line1=address_line1,
            city=city,
            state=state,
            country=country,
            pincode=pincode,
            address_type=address_type,
            is_default=is_default,
        )
        messages.success(request, "Address added successfully.")
        return redirect("accounts:address_list")

    return render(request, "accounts/address/add_address.html")


@never_cache
@user_login_required
def address_edit(request, address_id):
    address = get_object_or_404(UserAddress, id=address_id, user=request.user)

    if request.method == "POST":
        form_data = request.POST.dict()
        address_line1 = request.POST.get("address_line1", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()       
        country = request.POST.get("country", "").strip()    
        pincode = request.POST.get("pincode", "").strip()
        address_type = request.POST.get("address_type", "").strip()

        if not all([address_line1, city, state, country, pincode]):
            messages.error(request, "All fields are required.")
            return render(request, "accounts/address/edit_address.html", {
                "address": address, "form_data": form_data
            })

        if not address_type:
            messages.error(request, "Address type is required.")
            return render(request, "accounts/address/edit_address.html", {
                "address": address, "form_data": form_data
            })

        is_default = request.POST.get("is_default") == "on"

        if is_default:
            UserAddress.objects.filter(user=request.user).update(is_default=False)

        address.address_line1 = address_line1
        address.city = city
        address.state = state
        address.country = country
        address.pincode = pincode
        address.address_type = address_type
        address.is_default = is_default
        address.save()

        messages.success(request, "Address updated successfully.")
        return redirect("accounts:address_list")

    return render(request, "accounts/address/edit_address.html", {"address": address})


@never_cache
@user_login_required
def address_delete(request, address_id):
    address = get_object_or_404(UserAddress, id=address_id, user=request.user)
    address.delete()
    messages.success(request, "Address deleted.")
    return redirect("accounts:address_list")