import requests
from bs4 import BeautifulSoup

def fetch_cs2_cases():
    url = "https://www.csgodatabase.com/cases/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    case_elements = soup.select("div.case-listing h3")
    return [case.get_text(strip=True) for case in case_elements]
