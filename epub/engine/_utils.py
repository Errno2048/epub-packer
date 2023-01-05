import requests
import re
import os

def file_escape(s):
    return re.sub(r'[\t:/\\*?<>|"\']', r'_', s)

def ext(path: str) -> str:
    rf = path.rfind(os.extsep)
    if rf >= 0:
        return path[rf + 1:]
    return ""

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.30'}

def requests_get(url, retry=10):
    count = 0
    while count < retry:
        try:
            res = requests.get(url, headers=HEADERS, data={})
            if res.status_code >= 200 and res.status_code < 300:
                return res.content
        except Exception as e:
            print(e)
            pass
        count += 1
    return None
