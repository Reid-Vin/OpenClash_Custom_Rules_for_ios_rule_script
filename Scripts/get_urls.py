import requests
from bs4 import BeautifulSoup
import os

def main():
    url = "https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # 找到所有的表格
    tables = soup.find_all("table")

    all_urls = []

    # 提取每个表格内的链接并按表格标题进行分类
    for table in tables:
        # 获取表格标题
        category = table.find_previous("h2").text.strip()
        # 获取表格中的链接
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            for cell in cells:
                link = cell.find("a")
                if link:
                    name = link.text.strip()
                    url = link["href"]
                    all_urls.append((category, name, url))

    # 将链接按照表格标题进行分类和格式化
    categorized_urls = {}
    for category, name, url in all_urls:
        if category not in categorized_urls:
            categorized_urls[category] = []
        categorized_urls[category].append(f"{name}: {url}")

    # 将分类后的链接写入文件
    output_file = os.getenv("OUTPUT_FILE")
    with open(output_file, "w") as f:
        for category, urls in categorized_urls.items():
            f.write(f"{category}:\n")
            for url in urls:
                f.write(f"    {url}\n")

if __name__ == "__main__":
    main()
