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
    with open('Urls/All_Urls.list', 'w') as f:
        # Iterate over each table
        for table in tables:
            # Find the table header and write it to the file
            header = table.find('thead').find('tr').find('th').text
            f.write(f'\\n{header}\\n')

            # Find all rows in the table body
            rows = table.find('tbody').find_all('tr')
            # Iterate over each row
            for row in rows:
                # Find all links in the row
                links = row.find_all('a')
                # Iterate over each link
                for link in links:
                    # Write the link text and URL to the file
                    f.write(f'{link.text}: {link["href"]}\\n')

    # Open the output file
    with open('Urls/All_Urls.md', 'w') as f:
        # Iterate over each table
        for table in tables:
            # Find the table header and write it to the file
            header = table.find('thead').find('tr').find('th').text
            f.write(f'\\n{header}\\n')

            # Find all rows in the table body
            rows = table.find('tbody').find_all('tr')
            # Iterate over each row
            for row in rows:
                # Find all links in the row
                links = row.find_all('a')
                # Iterate over each link
                for link in links:
                    # Write the link text and URL to the file
                    f.write(f'{link.text}: {link["href"]}\\n')

if __name__ == "__main__":
    scrape_webpage()
