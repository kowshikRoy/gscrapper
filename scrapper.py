import argparse
import csv
import os
import random
import re
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pandas as pd
import undetected_chromedriver as uc
from bs4 import BeautifulSoup, Tag
from selenium.webdriver.chrome.options import Options

ssl._create_default_https_context = ssl._create_unverified_context
lock = threading.Lock()

# --- Constants ---

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15'
]

CSV_FILE = "scrapped_gscholar.csv"
BIB_FILE = "scrapped_gscholar.bib"
COLUMNS = ['Page_Index', 'Order_in_Page', 'Title', 'Year', 'Authors', 'Publication_Info', 'Abstract', 'Link', 'DOI', 'Citations', 'Scholar_Link', 'Author_Keywords']


# --- Helper Functions ---

def wait(min_seconds: int = 5, max_seconds: int = 15):
    """Waits for a random amount of time between min_seconds and max_seconds."""
    print("Waiting for a few secs...")
    time.sleep(random.randrange(min_seconds, max_seconds))
    print("Waiting done. Continuing...\n")


def extract_year(text: str) -> Optional[int]:
    """Extracts the year from a string using regex."""
    match = re.search(r'\b\d{4}\b', text)
    return int(match.group(0)) if match else None


def extract_citations(element: Optional[Tag]) -> Optional[int]:
    """Extracts the number of citations from a BeautifulSoup element."""
    if not element:
        return None
    citation_link = element.find('a', href=lambda href: href and 'cites=' in href)
    if citation_link:
        match = re.search(r'Cited by (\d+)', citation_link.text)
        if match:
            return int(match.group(1))
    return None


def generate_bibtex(entry: pd.Series) -> str:
    """Generates a BibTeX entry from a pandas Series."""
    try:
        author_lastname = entry['Authors'].split(',')[0].split(' ')[-1].strip()
        year = int(entry['Year']) if pd.notna(entry['Year']) else 'NoYear'
        first_title_word = entry['Title'].split(' ')[0].strip()
        bib_key = f"{author_lastname}{year}{first_title_word}"
    except (AttributeError, IndexError, KeyError):
        bib_key = f"entry{random.randint(1000, 9999)}"

    bibtex_parts = [f"@article{{{bib_key},"]
    if pd.notna(entry.get('Title')):
        bibtex_parts.append(f"  title={{{entry['Title']}}},")
    if pd.notna(entry.get('Authors')):
        bibtex_parts.append(f"  author={{{entry['Authors']}}},")
    if pd.notna(entry.get('Publication_Info')):
        bibtex_parts.append(f"  journal={{{entry['Publication_Info']}}},")
    if pd.notna(entry.get('Year')):
        bibtex_parts.append(f"  year={{{int(entry['Year'])}}},")
    if pd.notna(entry.get('DOI')):
        bibtex_parts.append(f"  doi={{{entry['DOI']}}},")
    if pd.notna(entry.get('Abstract')):
        bibtex_parts.append(f"  abstract={{{entry['Abstract']}}},")
    bibtex_parts.append("}")
    return "\n".join(bibtex_parts)


def extract_paper_details(url: str) -> Dict[str, Any]:
    """Extracts detailed information from the paper's page."""
    details = {'Abstract': None, 'Author_Keywords': None, 'DOI': None}
    options = Options()
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
    options.add_argument('--proxy-server=socks5://122.0.0.1:9050')
    with lock:
        driver = uc.Chrome(options=options, headless=True)
    try:
        driver.get(url)
        soup = BeautifulSoup(driver.page_source, "lxml")

        # Extract Abstract
        abstract_selectors = ['div.abstract', 'div#abstract', 'section.abstract']
        for selector in abstract_selectors:
            abstract_element = soup.select_one(selector)
            if abstract_element:
                details['Abstract'] = abstract_element.get_text(strip=True)
                break

        # Extract Keywords
        keyword_selectors = ['div.keywords', 'div#keywords', 'meta[name="keywords"]']
        for selector in keyword_selectors:
            keyword_element = soup.select_one(selector)
            if keyword_element:
                if keyword_element.name == 'meta':
                    details['Author_Keywords'] = keyword_element.get('content')
                else:
                    details['Author_Keywords'] = keyword_element.get_text(strip=True)
                break
        
        # Extract DOI
        doi_selectors = ['a[href*="doi.org"]', 'meta[name="citation_doi"]']
        for selector in doi_selectors:
            doi_element = soup.select_one(selector)
            if doi_element:
                if doi_element.name == 'meta':
                    details['DOI'] = doi_element.get('content')
                else:
                    details['DOI'] = doi_element.get('href')
                break

    except Exception as e:
        print(f"Could not fetch details from {url}: {e}")
    finally:
        driver.quit()
    return details


def parse_search_result(job_element: Tag, current_page_index: int, order_in_page: int, scraped_links: set) -> Optional[Dict[str, Any]]:
    """Parses a single search result from a BeautifulSoup element."""
    links = job_element.find("a")
    if not links:
        return None

    link_url = links["href"]

    if link_url in scraped_links:
        print(f"Skipping already scraped link: {link_url}")
        return None

    title_element = links.text.strip()

    ref_element = job_element.find("div", class_="gs_a")
    ref_element_text = ref_element.text if ref_element else ""

    authors_part = ref_element_text.split(' - ')[0]
    publication_part = ' - '.join(ref_element_text.split(' - ')[1:]) if ' - ' in ref_element_text else ""

    year = extract_year(ref_element_text)

    abstract_element = job_element.find("div", class_="gs_rs")
    abstract = abstract_element.text.strip() if abstract_element else None

    pdf_link_element = job_element.find("div", class_="gs_or_ggsm")
    pdf_link = pdf_link_element.find("a")["href"] if pdf_link_element and pdf_link_element.find("a") else None

    link = pdf_link if pdf_link else link_url

    doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', link, re.IGNORECASE)
    doi = doi_match.group(0) if doi_match else None

    citations_element = job_element.find("div", class_="gs_fl")
    citations = extract_citations(citations_element)

    entry_data = {
        'Page_Index': current_page_index,
        'Order_in_Page': order_in_page,
        'Title': title_element,
        'Year': year,
        'Authors': authors_part,
        'Publication_Info': publication_part,
        'Abstract': abstract,
        'Link': link,
        'DOI': doi,
        'Citations': citations,
        'Scholar_Link': link_url,
    }

    if link:
        print(f"Fetching details from: {link}")
        detailed_info = extract_paper_details(link)
        entry_data.update(detailed_info)


    print(f"Page: {current_page_index}, Order: {order_in_page}")
    print(f"Title: {title_element}")
    print(f"Year: {year}")
    print(f"Authors: {authors_part}")
    print(f"Publication Info: {publication_part}")
    print(f"Abstract: {entry_data.get('Abstract', 'N/A')}")
    print(f"Link: {link}")
    print(f"DOI: {entry_data.get('DOI', 'N/A')}")
    print(f"Citations: {citations}")
    print(f"Author Keywords: {entry_data.get('Author_Keywords', 'N/A')}")
    print("-" * 20)

    return entry_data


def load_existing_data() -> pd.DataFrame:
    """Loads existing data from CSV_FILE or creates a new DataFrame."""
    if os.path.exists(CSV_FILE):
        print(f"Found existing data in {CSV_FILE}. Resuming scrape.")
        df = pd.read_csv(CSV_FILE)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
    else:
        df = pd.DataFrame(columns=COLUMNS)
    return df


def save_data(df: pd.DataFrame, new_results: List[Dict[str, Any]]):
    """Saves new results to the CSV file."""
    if new_results:
        new_df = pd.DataFrame(new_results, columns=COLUMNS)
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(CSV_FILE, index=False, quoting=csv.QUOTE_ALL)
        print(f"Saved {len(new_results)} new results to {CSV_FILE}")
    return df


def generate_bib_file():
    """Generates a .bib file from the scraped data."""
    if not os.path.exists(CSV_FILE):
        return

    final_df = pd.read_csv(CSV_FILE)
    if not final_df.empty:
        final_df['BibTeX'] = final_df.apply(generate_bibtex, axis=1)
        bibtex_entries = final_df['BibTeX'].dropna().tolist()
        if bibtex_entries:
            with open(BIB_FILE, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(bibtex_entries))
            print(f"Successfully generated {BIB_FILE} with {len(bibtex_entries)} entries.")


def scrape_page(page_num: int, base_url: str, scraped_links: set) -> List[Dict[str, Any]]:
    """Scrapes a single page of Google Scholar results."""
    options = Options()
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
    options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
    with lock:
        driver = uc.Chrome(options=options, headless=True)
    new_results = []
    current_page_index = page_num // 10 + 1
    try:
        print(f"Scraping page {current_page_index}")

        if 'start=' in base_url:
            current_url = re.sub(r'start=\d+', f'start={page_num}', base_url)
        else:
            current_url = f"{base_url}&start={page_num}"

        driver.get(current_url)
        soup = BeautifulSoup(driver.page_source, "lxml")
        wait(2, 5)

        results_container = soup.find("div", id="gs_res_ccl_mid")
        if not results_container:
            print(f"Could not find results container for page {current_page_index}.")
            return []

        job_elements = results_container.find_all("div", class_="gs_ri")
        if not job_elements:
            print(f"No results found on page {current_page_index}.")
            return []

        for i, job_element in enumerate(job_elements):
            entry_data = parse_search_result(job_element, current_page_index, i + 1, scraped_links)
            if entry_data:
                new_results.append(entry_data)
        print(f"Successfully scraped page {current_page_index}, found {len(new_results)} new results.")
    except Exception as e:
        print(f"An error occurred while scraping page {current_page_index}: {e}")
    finally:
        driver.quit()
    return new_results


def main():
    """Main function to run the Google Scholar scraper."""
    parser = argparse.ArgumentParser(description='Scrape Google Scholar search results.')
    parser.add_argument('url', nargs='?',
                        default='https://scholar.google.com/scholar?start=0&q=%22autism%22+and+%22bangladesh%22&hl=en&as_sdt=0,48&as_ylo=2020&as_yhi=2025&as_rr=1&as_vis=1',
                        help='The Google Scholar search URL to scrape.')
    parser.add_argument('--num-pages', type=int, default=10, help='Number of pages to scrape.')
    parser.add_argument('--max-workers', type=int, default=5, help='Maximum number of parallel workers.')
    args = parser.parse_args()
    base_url = args.url

    df = load_existing_data()
    scraped_links = set(df['Scholar_Link'].dropna())

    start_page = 0
    if not df.empty and 'Page_Index' in df.columns and df['Page_Index'].notna().any():
        last_page = df['Page_Index'].max()
        start_page = int(last_page)
        print(f"Resuming scrape from page {start_page + 1}")
    else:
        match = re.search(r'start=(\d+)', base_url)
        if match:
            start_page = int(match.group(1)) // 10
    
    pages_to_scrape = [((start_page + i) * 10) for i in range(args.num_pages)]
    all_new_results = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_page = {executor.submit(scrape_page, page_num, base_url, scraped_links): page_num for page_num in pages_to_scrape}
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                results = future.result()
                all_new_results.extend(results)
            except Exception as exc:
                print(f'Page {page_num // 10 + 1} generated an exception: {exc}')

    df = save_data(df, all_new_results)
    generate_bib_file()
    print("Job finished, Godspeed you! Cite us.")


if __name__ == "__main__":
    main()