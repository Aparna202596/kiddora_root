from decimal import Decimal

import requests


def convert_currency(amount, from_currency="INR", to_currency="USD"):
    try:
        url = "https://api.frankfurter.app/latest"
        resp = requests.get(
            url,
            params={"from": from_currency, "to": to_currency},
            timeout=5,
        )
        resp.raise_for_status()
        rate = resp.json()["rates"][to_currency]
    except Exception:
        rate = 0.012  # fallback: ~1 INR = 0.012 USD
    return round(float(amount) * rate, 2)
