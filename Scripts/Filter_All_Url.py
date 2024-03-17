import requests
import time
import os
from bs4 import BeautifulSoup


def scrape_webpage_with_retry():
    max_retry = 3
    retry_delay = [60, 180, 600]  # 重试延迟时间，分别为1分钟、3分钟、10分钟

    for attempt in range(max_retry):
        try:
            # Send a GET request to the webpage
            response = requests.get('https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash')
            # 控制台输出接收到的网页信息
            print(response.text)
            # 如果 response 为空，则输出信息并进行重试
            if not response:
                print("未获取到网页信息，进行重试...")
                time.sleep(retry_delay[attempt])
                continue
            
            # Parse the HTML content of the page with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all tables in the webpage
            tables = soup.find_all('table')

            # Open the output file
            with open('Urls/All_Urls.list', 'w') as f:
                # Iterate over each table
                for table in tables:
                    # Find the table header and write it to the file
                    header = table.find('thead').find('tr').find('th').text
                    f.write(f'\n{header}\n')
                    print(f'Writing to file: \n{header}\n')

                    # Find all rows in the table body
                    rows = table.find('tbody').find_all('tr')
                    # Iterate over each row
                    for row in rows:
                        # Find all links in the row
                        links = row.find_all('a')
                        # Iterate over each link
                        for link in links:
                            # Remove the slashes and quotes from the link URL
                            url = link["href"].replace("\\", "").replace("\"", "")
                            # Write the link text and URL to the file
                            f.write(f'{link.text}: {url}\n')
                            print(f'Writing to file: {link.text}: {url}\n')

            # Open the output file
            with open('Urls/All_Urls_No_Name.list', 'w') as f:
                # Iterate over each table
                for table in tables:
                    # Find the table header and write it to the file
                    header = table.find('thead').find('tr').find('th').text
                    f.write(f'\n{header}\n')
                    print(f'Writing to file2: \n{header}\n')

                    # Find all rows in the table body
                    rows = table.find('tbody').find_all('tr')
                    # Iterate over each row
                    for row in rows:
                        # Find all links in the row
                        links = row.find_all('a')
                        # Iterate over each link
                        for link in links:
                            # Replace "github.com" with "raw.githubusercontent.com"
                            url = link["href"].replace("github.com", "raw.githubusercontent.com")
                            # Remove "/tree" from the URL
                            url = url.replace("/tree", "")
                            # Get the name of the file
                            file_name = url.split('/')[-1]
                            # Add the file name and ".list" to the end of the URL
                            url = url + "/" + file_name + ".list"
                            # Remove the slashes and quotes from the URL
                            url = url.replace("\\", "").replace("\"", "")
                            # Write the URL to the file
                            f.write(f'{url}\n')
                            print(f'Writing to file2: {url}\n')

            # 如果成功获取到数据，直接退出循环
            break

        except Exception as e:
            print(f"Error occurred: {e}")
            if attempt < max_retry - 1:
                print(f"进行第 {attempt+1} 次重试...")
                time.sleep(retry_delay[attempt])
            else:
                print("失败次数过多，请稍后再试。")
                return


if __name__ == "__main__":
    scrape_webpage_with_retry()
    # 定义文件路径
    file_paths = ["Urls/All_Urls.list", "Urls/All_Urls_No_Name.list"]
    # 检查文件是否存在
    for file_path in file_paths:
        if os.path.exists(file_path):
            print(f"文件 {file_path} 存在。")
        else:
            print(f"文件 {file_path} 不存在。")
