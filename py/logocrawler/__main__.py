from bs4 import BeautifulSoup
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import urllib3
import os
import csv
import json
import re
urllib3.disable_warnings()

def normalize_url(domain, url):
    """
    - Remove unecessary param for example: */favicon_apple-touch.svg?auto=webp&format=png -> */favicon_apple-touch.svg
    - Add protocol if icon url start with '//' for example: //www.apnic.net/favicon-32x32.png -> https://www.apnic.net/favicon-32x32.png
    - Add protocol+domain if url is path, for example: /favicon.ico -> https://domain/favicon.ico
    """
    if url.startswith('//'):
        url = 'https:'+url
    elif 'http' not in url and not 'data:image' in url:
        if not url.startswith('/'):
            # To handle 'favicon.ico'
            url = 'https://'+domain+'/'+url
        else:
            url = 'https://'+domain+url

    if '?' in url:
        url = url.split('?')[0]
    return url

def extract_favicon(domain, element):
    """ If no logo is found from the jsonld, the script will use favicon as a fallback
    Sequence:
    - If only 1 icon found, return it
    - If more than 1 PNG found, return the longest string, this is the easiest possible way to get the highest resolution
      for example 32x32 vs 180x180, the script will return 180x180 most of the time since usually image file is saved in same exact path
      PNG is prioritized because usually it have higher res than ico
    - If more than 1 ICO found, apply same logic with PNG
    - For the absoulte fallback, it will return the first image found """

    urls = list(set([icon['href'] for icon in element]))

    if not urls:
        return None

    elif len(urls) == 1:
        return normalize_url(domain, urls[0])


    pngs = [url for url in urls if 'png' in url]
    icos = [url for url in urls if 'ico' in url]

    if pngs:
        return normalize_url(domain, max(pngs))
    elif icos:
        return normalize_url(domain, max(icos))

    return normalize_url(domain, urls[0])
    

def extract_json(domain, element):
    """ To extract information availabble on JSON-LD, usually have logo available, not favicon.
    Possible logo url location based on my observation is:
    - data['logo']
    - data['logo']['logo']
    - data['publisher']['logo']['url']
    - data['@graph'][-1]['logo'] """
    
    logo = None
    for x in element:
        if 'logo' in x.string:
            jsonld = json.loads(x.string)
            if isinstance(jsonld, list):
                for line in jsonld:
                    if 'logo' in line:
                        jsonld = line
                        break
                else:
                    jsonld = jsonld[0]
            if 'logo' in jsonld.keys():
                logo = jsonld['logo']
                if isinstance(logo, dict):
                    logo = logo['url']
                    break

            elif 'publisher' in jsonld.keys():
                if 'logo' in jsonld['publisher'].keys():
                    logo = jsonld['publisher']['logo']['url']
                    break

            elif '@graph' in jsonld.keys():
                logo_keys = [index for index in jsonld['@graph'] if 'logo' in index.keys()]
                for line in logo_keys:
                    logo = line['logo']
                    if isinstance(logo, dict):
                        logo = logo['url']

    if logo:
        return normalize_url(domain, logo)
    return None

def fetch_icon(domain):
    try:
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        }

        response = requests.get('https://'+domain, verify=False, timeout=10, headers=headers).text
        soup = BeautifulSoup(response, 'html.parser')

        check_script = soup.find_all('script', type="application/ld+json")
        logo_url = None
        if check_script:
            logo_url = extract_json(domain, check_script)
        if logo_url:
            return [domain, logo_url]
        else:
            icon_search = soup.find_all('link',rel=re.compile(r'icon'))
            logo_url = extract_favicon(domain, icon_search)
            if logo_url:
                return [domain, logo_url]

        return [domain,logo_url]


    except Exception as e:
        return [domain,None]


string_input = sys.stdin.read().strip().split("\n")
domain_list = [x.strip() for x in string_input]

writer = csv.writer(sys.stdout,lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
with ThreadPoolExecutor(max_workers=2*os.cpu_count()) as pool:
    futures = [pool.submit(fetch_icon, url) for url in domain_list]
    for finished in as_completed(futures):
        result = finished.result()
        writer.writerow(result)
