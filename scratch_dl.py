import requests
import re

url = 'https://www.douyin.com/video/7683569041939647795'
print(f'Testing dlpanda for {url}')
r = requests.get(f'https://dlpanda.com/vi?url={url}&token=G7eRpMaa', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'})
# The video link usually looks like <a href="https://... video ...">Download</a>
# Let's just print all anchor hrefs to see what we get
links = re.findall(r'href="([^"]+)"', r.text)
video_links = [l for l in links if 'douyincdn.com' in l or 'douyin.com' in l or 'video' in l.lower()]
print('Found potential links:')
for l in video_links:
    print(l[:150])
