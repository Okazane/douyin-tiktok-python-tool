import requests
import re
import json

url = 'https://www.douyin.com/video/7683569041939647795'
print(f'Testing godownloader for {url}')
data = {'url': url}
r = requests.post('https://godownloader.com/api/douyin-info', data=data, headers={'User-Agent': 'Mozilla/5.0'})
print('Status:', r.status_code)
try:
    print(r.json())
except:
    print(r.text[:200])

print("\nTesting douyin.wtf")
r2 = requests.get(f'https://api.douyin.wtf/api?url={url}', headers={'User-Agent': 'Mozilla/5.0'})
print('Status:', r2.status_code)
try:
    print(r2.json())
except:
    print(r2.text[:200])
