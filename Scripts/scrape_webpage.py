import requests
from bs4 import BeautifulSoup

def scrape_webpage():
    # Send a GET request to the webpage
    response = requests.get('https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash')

    # Parse the HTML content of the page with BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all tables in the webpage
    tables = soup.find_all('table')

    # Open the output files
    with open('Urls/All_Urls.list', 'w') as f, open('Urls/All_Urls_No_Name.list', 'w') as f_no_name:
        # Iterate over each table
        for table in tables:
            # Find the table header and write it to the files
            header = table.find('thead').find('tr').find('th').text
            f.write(f'\n{header}\n')
            f_no_name.write(f'\n{header}\n')

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
                    # Write the link text and URL to the first file
                    f.write(f'{link.text}: {url}\n')
                    
                    # Convert the URL to raw format and write it to the second file
                    raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/tree", "") + "/" + link.text + "/" + link.text + ".list"
                    f_no_name.write(f'{raw_url}\n')

if __name__ == "__main__":
    scrape_webpage()
