import requests
from django.conf import settings

def get_paypal_access_token():
    response = requests.post(
        "https://api-m.sandbox.paypal.com/v1/oauth2/token",
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
    )
    return response.json()["access_token"]
