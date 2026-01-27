import requests
def convert_currency(amount, from_currency="INR", to_currency="USD"):
    url = f"https://api.exchangerate.host/convert"
    response = requests.get(url, params={
        "from": from_currency,
        "to": to_currency,
        "amount": amount
    })
    data = response.json()
    return round(data["result"], 2)
