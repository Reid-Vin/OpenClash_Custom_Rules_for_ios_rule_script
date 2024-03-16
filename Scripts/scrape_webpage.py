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
            f.write(f'\n{header}\n')

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
                    url = url + "/" + file_name + "/" + file_name + ".list"
                    # Write the URL to the file
                    f.write(f'{url}\n')

if __name__ == "__main__":
    scrape_webpage()
