import requests
from bs4 import BeautifulSoup
import re

# 请求网页
url = 'https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash'
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# 找到所有表格
tables = soup.find_all('table')

# 提取表格数据并输出
for table in tables:
    title = table.find_previous('h2').text.strip()
    print(f"表格标题：{title}")
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['th', 'td'])
        for cell in cells:
            link = cell.find('a')
            if link:
                href = link.get('href')
                print(href)

# 添加一些调试输出
print("网页爬取完成！")
