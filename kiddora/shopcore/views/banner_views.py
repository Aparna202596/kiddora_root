# ============================================================
# shopcore/views/banner_views.py
# Admin CRUD for Banner model + home page view that passes banners
# ============================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required

from accounts.decorators import admin_login_required
from shopcore.models import Banner


# ─────────────────────────────────────────────────────────────
# HOME PAGE VIEW  (user-facing)
# Passes live HERO and SECONDARY banners to the home template.
# ─────────────────────────────────────────────────────────────

def home_view(request):
    """
    Public home page.  Passes:
      hero_banners      — up to 6 live HERO banners for the carousel
      secondary_banners — up to 4 live SECONDARY banners for the grid
    """
    live_banners = [b for b in Banner.objects.filter(is_active=True) if b.is_live()]

    hero_banners      = [b for b in live_banners if b.slot == "HERO"][:6]
    secondary_banners = [b for b in live_banners if b.slot == "SECONDARY"][:4]

    return render(request, "store/homes.html", {
        "hero_banners":      hero_banners,
        "secondary_banners": secondary_banners,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_banner_list(request):
    search = request.GET.get("search", "").strip()
    slot_f = request.GET.get("slot", "")

    banners = Banner.objects.all()
    if search:
        banners = banners.filter(title__icontains=search)
    if slot_f:
        banners = banners.filter(slot=slot_f)

    return render(request, "banner/admin_banner_list.html", {
        "banners":      banners,
        "search":       search,
        "slot_f":       slot_f,
        "slot_choices": Banner.SLOT_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — ADD
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_add_banner(request):
    if request.method == "POST":
        title         = request.POST.get("title", "").strip()
        subtitle      = request.POST.get("subtitle", "").strip()
        cta_text      = request.POST.get("cta_text", "Shop Now").strip()
        cta_url       = request.POST.get("cta_url", "/products/user/products/").strip()
        badge_text    = request.POST.get("badge_text", "").strip()
        slot          = request.POST.get("slot", "HERO")
        display_order = request.POST.get("display_order", 0)
        start_date    = request.POST.get("start_date") or None
        end_date      = request.POST.get("end_date")   or None
        image         = request.FILES.get("image")

        if not title:
            messages.error(request, "Title is required.")
            return render(request, "banner/admin_banner_form.html", {
                "slot_choices": Banner.SLOT_CHOICES,
                "form_data": request.POST,
            })
        if not image:
            messages.error(request, "Banner image is required.")
            return render(request, "banner/admin_banner_form.html", {
                "slot_choices": Banner.SLOT_CHOICES,
                "form_data": request.POST,
            })

        Banner.objects.create(
            title=title,
            subtitle=subtitle,
            image=image,
            cta_text=cta_text,
            cta_url=cta_url,
            badge_text=badge_text,
            slot=slot,
            display_order=int(display_order),
            start_date=start_date,
            end_date=end_date,
            is_active=True,
        )
        messages.success(request, f'Banner "{title}" created.')
        return redirect("shopcore:admin_banner_list")

    return render(request, "banner/admin_banner_form.html", {
        "slot_choices": Banner.SLOT_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — EDIT
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_edit_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)

    if request.method == "POST":
        banner.title         = request.POST.get("title", banner.title).strip()
        banner.subtitle      = request.POST.get("subtitle", "").strip()
        banner.cta_text      = request.POST.get("cta_text", "Shop Now").strip()
        banner.cta_url       = request.POST.get("cta_url", "/products/user/products/").strip()
        banner.badge_text    = request.POST.get("badge_text", "").strip()
        banner.slot          = request.POST.get("slot", banner.slot)
        banner.display_order = int(request.POST.get("display_order", banner.display_order))
        banner.start_date    = request.POST.get("start_date") or None
        banner.end_date      = request.POST.get("end_date")   or None

        new_image = request.FILES.get("image")
        if new_image:
            # Delete old image file before replacing
            if banner.image:
                try:
                    import os
                    if os.path.isfile(banner.image.path):
                        os.remove(banner.image.path)
                except Exception:
                    pass
            banner.image = new_image

        if not banner.title:
            messages.error(request, "Title is required.")
            return render(request, "banner/admin_banner_form.html", {
                "banner":       banner,
                "slot_choices": Banner.SLOT_CHOICES,
            })

        banner.save()
        messages.success(request, f'Banner "{banner.title}" updated.')
        return redirect("shopcore:admin_banner_list")

    return render(request, "banner/admin_banner_form.html", {
        "banner":       banner,
        "slot_choices": Banner.SLOT_CHOICES,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — DELETE
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_delete_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)
    if request.method == "POST":
        title = banner.title
        # Remove the image file from disk
        if banner.image:
            try:
                import os
                if os.path.isfile(banner.image.path):
                    os.remove(banner.image.path)
            except Exception:
                pass
        banner.delete()
        messages.success(request, f'Banner "{title}" deleted.')
        return redirect("shopcore:admin_banner_list")
    # GET → confirm page (uses confirm_modal.html pattern)
    return render(request, "banner/admin_banner_list.html", {
        "banners":      Banner.objects.all(),
        "slot_choices": Banner.SLOT_CHOICES,
        "delete_target": banner,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN — TOGGLE ACTIVE  (POST)
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_toggle_banner(request, banner_id):
    banner = get_object_or_404(Banner, id=banner_id)
    if request.method == "POST":
        banner.is_active = not banner.is_active
        banner.save()
        state = "activated" if banner.is_active else "deactivated"
        messages.success(request, f'Banner "{banner.title}" {state}.')
    return redirect("shopcore:admin_banner_list")