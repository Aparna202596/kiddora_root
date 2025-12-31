from django.shortcuts import render, redirect, get_object_or_404
from accounts.models import UserAddress
from accounts.decorators import user_login_required


@user_login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, "accounts/profile/addresses.html", {"addresses": addresses})


@user_login_required
def address_add(request):
    if request.method == "POST":
        is_default = request.POST.get("is_default") == "on"
        if is_default:
            UserAddress.objects.filter(user=request.user).update(is_default=False)
        UserAddress.objects.create(
            user=request.user,
            address_line1=request.POST.get("address_line1"),
            city=request.POST.get("city"),
            state=request.POST.get("state"),
            country=request.POST.get("country"),
            pincode=request.POST.get("pincode"),
            address_type=request.POST.get("address_type"),
            is_default=is_default
        )
        return redirect("accounts:address_list")
    return render(request, "accounts/profile/add_address.html")


@user_login_required
def address_edit(request, address_id):
    address = get_object_or_404(UserAddress, id=address_id, user=request.user)
    if request.method == "POST":
        is_default = request.POST.get("is_default") == "on"
        if is_default:
            UserAddress.objects.filter(user=request.user).update(is_default=False)
        address.address_line1 = request.POST.get("address_line1")
        address.city = request.POST.get("city")
        address.state = request.POST.get("state")
        address.country = request.POST.get("country")
        address.pincode = request.POST.get("pincode")
        address.address_type = request.POST.get("address_type")
        address.is_default = is_default
        address.save()
        return redirect("accounts:address_list")
    return render(request, "accounts/profile/edit_address.html", {"address": address})


@user_login_required
def address_delete(request, address_id):
    address = get_object_or_404(UserAddress, id=address_id, user=request.user)
    address.delete()
    return redirect("accounts:address_list")

