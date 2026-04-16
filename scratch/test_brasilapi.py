import requests
import json

def test_cnpj(cnpj):
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    response = requests.get(url)
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=4, ensure_ascii=False))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

# Using a public CNPJ for testing (e.g., Google or similar if known, or just a placeholder)
# Google Brasil: 06.990.590/0001-23
test_cnpj("06990590000123")
