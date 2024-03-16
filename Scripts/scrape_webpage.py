import requests
from bs4 import BeautifulSoup

def scrape_webpage():
    # Send a GET request to the webpage
    response = requests.get('https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash')

    # Parse the HTML content of the page with BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all tables in the webpage
    tables = soup.find_all('table')

    # Open the output file
    with open('Urls/All_Urls.md', 'w', encoding='utf-8') as f_md, open('Urls/All_Urls.list', 'w', encoding='utf-8') as f_list:
        # Iterate over each table
        for table in tables:
            # Find the table header and write it to the files
            header = table.find('thead').find('tr').find('th').text
            f_md.write(f'## 分流类型：{header}\\n')
            f_list.write(f'{header}\\n\\n')

            # Find all rows in the table body
            rows = table.find('tbody').find_all('tr')
            # Iterate over each row
            for row in rows:
                # Find all links in the row
                links = row.find_all('a')
                # Iterate over each link
                for link in links:
                    # Write the link text and URL to the files
                    f_md.write(f'- {link.text}\\n')
                    f_list.write(f'{link.text}: {link["href"]}\\n')
            f_md.write('\\n')
            f_list.write('\\n\\n')

if __name__ == "__main__":
    scrape_webpage()
