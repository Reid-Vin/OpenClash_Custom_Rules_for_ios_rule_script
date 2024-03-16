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

    # 提取每个表格内的链接
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            for cell in cells:
                link = cell.find("a")
                if link:
                    url = link["href"]
                    all_urls.append(url)

    # 将链接写入文件
    output_file = os.getenv("OUTPUT_FILE")
    with open(output_file, "w") as f:
        for url in all_urls:
            f.write(url + "\n")

if __name__ == "__main__":
    main()
