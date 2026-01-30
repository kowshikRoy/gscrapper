import argparse
import csv
import os
import random
import re
import socket
import ssl
import subprocess
import threading
import time
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import Any, Dict, List, Optional, Tuple, Callable

import pandas as pd
import queue
import undetected_chromedriver as uc
from bs4 import BeautifulSoup, Tag
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

ssl._create_default_https_context = ssl._create_unverified_context
lock = threading.Lock()

# --- Constants ---

# USER_AGENTS removed to allow undetected-chromedriver to handle it naturally

CSV_FILE = "scrapped_gscholar.csv"
BIB_FILE = "scrapped_gscholar.bib"
COLUMNS = ['Page_Index', 'Order_in_Page', 'Title', 'Year', 'Authors', 'Publication_Info', 'Abstract', 'Snippet', 'Link', 'DOI', 'Citations', 'Scholar_Link', 'Author_Keywords', 'First_Author_Link', 'Citation_Link', 'Citation_View_PDF_Link']
LOG_FILE = "scraper.log"

# --- Logging Configuration (Moved to separate function) ---

def setup_logging(log_file: str):
    # Remove existing handlers if any
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

# Compiled regex for year extraction
YEAR_PATTERN = re.compile(r'\b\d{4}\b')


# --- Helper Functions ---

def wait(min_ms: int = 0, max_ms: int = 1000):
    """Waits for a random amount of time between min_ms and max_ms milliseconds."""
    if min_ms >= max_ms:
         sleep_time_ms = min_ms
    else:
         sleep_time_ms = random.randrange(min_ms, max_ms)
    
    sleep_time_sec = sleep_time_ms / 1000.0
    logging.info(f"Waiting for {sleep_time_sec} secs...")
    time.sleep(sleep_time_sec)
    logging.info("Waiting done. Continuing...\n")






# Global lock for Tor restart to prevent concurrent restarts
tor_restart_lock = threading.Lock()
last_tor_restart_time = 0

def restart_tor_service(command: str) -> bool:
    """Restarts the Tor service using the provided shell command, with cooldown."""
    global last_tor_restart_time
    
    # Check if a restart happened recently (e.g., within 60 seconds)
    # This check is outside the lock for performance optimization
    if time.time() - last_tor_restart_time < 60:
        logging.info("Tor service was restarted recently. Skipping redundant restart.")
        return True

    with tor_restart_lock:
        # Double-check inside the lock to be thread-safe
        if time.time() - last_tor_restart_time < 60:
             logging.info("Tor service was restarted recently by another worker. Skipping.")
             return True

        try:
            logging.info(f"Restarting Tor service with command: {command}")
            # Mark the time BEFORE starting the process so blocked threads will see it immediately
            last_tor_restart_time = time.time() 
            subprocess.run(command, shell=True, check=True)
            logging.info("Tor service restart command executed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to restart Tor service: {e}")
            return False
        except Exception as e:
            logging.error(f"An unexpected error occurred restarting Tor: {e}")
            return False


def check_tor_connection(proxy_url: str) -> bool:
    """Checks if the Tor proxy is reachable."""
    try:
        # Parse proxy URL (e.g., socks5://127.0.0.1:9050)
        proxy_host = "127.0.0.1"
        proxy_port = 9050
        
        if "://" in proxy_url:
            try:
                parts = proxy_url.split("://")
                if len(parts) > 1:
                    address = parts[1]
                    if ":" in address:
                        proxy_host, proxy_port_str = address.split(":")
                        proxy_port = int(proxy_port_str)
                    else:
                        proxy_host = address
            except ValueError:
                 pass # Fallback to defaults

        logging.info(f"Checking Tor connection at {proxy_host}:{proxy_port}...")
        with socket.create_connection((proxy_host, proxy_port), timeout=5):
            logging.info(f"Tor proxy at {proxy_host}:{proxy_port} is reachable.")
            return True
            
    except Exception as e:
        logging.warning(f"Tor proxy is NOT reachable: {e}")
        return False


def safe_driver_get(driver: uc.Chrome, url: str, proxy: Optional[str] = None, headless: bool = True, tor_restart_cmd: Optional[str] = None, min_wait: int = 5000, max_wait: int = 15000, validator: Optional[Callable[[uc.Chrome], bool]] = None) -> Tuple[bool, bool, uc.Chrome]:
    """
    Safely navigates to a URL with built-in block detection and recovery.
    Returns: (success, should_stop, driver)
             success: True if page loaded and is not blocked.
             should_stop: True if explicit "No Results" found (only relevant for search pages, but harmless elsewhere).
             driver: The potentially updated driver object (if restarted).
    """
    max_retries = 3
    retry_count = 0
    current_headless = headless

    while retry_count <= max_retries:
        try:
            logging.info(f"Fetching URL: {url} (Attempt {retry_count + 1})")
            driver.get(url)
            
            # Simulate human behavior
            simulate_human_behavior(driver)
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            wait(min_wait, max_wait) # Basic wait after load

            page_text_lower = soup.get_text().lower()

            # Check for Blocks
            blocked = False
            if "unusual traffic" in page_text_lower or "captcha" in page_text_lower:
                logging.warning(f"Google Scholar blocked request (Captcha/Unusual Traffic).")
                blocked = True
            elif validator and not validator(driver):
                logging.warning(f"Validator failed. Suspected silent block.")
                blocked = True

            if blocked:
                # Option 1: Tor Service Restart
                if tor_restart_cmd:
                    logging.info("Attempting to restart Tor service...")
                    if restart_tor_service(tor_restart_cmd):
                        logging.info("Tor service restarted. Sleeping for 45 seconds...")
                        time.sleep(45)
                        
                        # Restart Driver to ensure clean state
                        logging.info("Restarting Chromedriver after Tor reset...")
                        try:
                            driver.quit()
                        except:
                            pass
                        

                        with lock:
                            options = Options()
                            options.add_argument("--window-size=1920,1080")
                            if current_headless:
                                options.add_argument("--headless=new")
                            if proxy:
                                options.add_argument(f'--proxy-server={proxy}')
                            # Force headless=False in uc init, handle headless via options
                            driver = uc.Chrome(options=options, headless=False, version_main=144)

                        retry_count += 1
                        continue
                    else:
                        logging.warning("Tor service restart failed.")



                print("\n" + "!"*40)
                print(f"CAPTCHA DETECTED (or validation failed)!")
                print("!"*40 + "\n")

                if current_headless:
                    logging.info("Headless mode detected. Restarting browser in VISIBLE mode...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    
                    with lock:
                        options = Options()
                        options.add_argument("--window-size=1920,1080")
                        if proxy:
                            options.add_argument(f'--proxy-server={proxy}')
                        driver = uc.Chrome(options=options, headless=False, version_main=144)
                    
                    current_headless = False
                    
                    logging.info("Reloading page in visible browser...")
                    driver.get(url)

                print("ACTION REQUIRED: Please solve the CAPTCHA in the opened browser window.")
                print("Once you have solved it and the results are visible, PRESS ENTER in this terminal to continue...")
                input()
                
                logging.info("User signaled ready. Resuming scrape...")
                continue
            
            return True, False, driver

        except Exception as e:
            logging.error(f"Error in safe_driver_get: {e}")
            # Network errors trigger retry
            retry_count += 1
            if retry_count > max_retries:
                logging.error(f"Max retries exceeded for URL: {url}")
                return False, False, driver
            time.sleep(random.uniform(2, 4)) # Reduced from 5-10s

    return False, False, driver


def simulate_human_behavior(driver: uc.Chrome):
    """Simulates human interaction to avoid detection."""
    try:
        # Random small scroll
        scroll_amount = random.randint(300, 700)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(0.1, 0.3)) # Speed up
        # Scroll back a bit or more
        driver.execute_script(f"window.scrollBy(0, -{random.randint(100, 300)});")
        time.sleep(random.uniform(0.1, 0.3)) # Speed up
    except Exception:
        pass


def extract_year(text: str) -> Optional[int]:
    """Extracts the year from a string using regex."""
    match = YEAR_PATTERN.search(text)
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





def find_citation_view_url(author_profile_url: str, paper_title: str, driver: uc.Chrome, proxy: Optional[str] = None, headless: bool = True, tor_restart_cmd: Optional[str] = None, min_wait: int = 5000, max_wait: int = 15000) -> Tuple[Optional[str], uc.Chrome]:
    """
    Navigates to the author's profile, expands the list, and finds the citation view link for the paper.
    Returns: (citation_link, driver)
    """
    citation_link = None
    
    if not author_profile_url.startswith("http"):
        author_profile_url = "https://scholar.google.com" + author_profile_url

    try:
        logging.info(f"Visiting author profile: {author_profile_url}")
        
        # Use safe_driver_get
        success, _, driver = safe_driver_get(driver, author_profile_url, proxy, headless, tor_restart_cmd, min_wait, max_wait)
        if not success:
             logging.warning("Failed to load author profile page.")
             return None, driver

        # Logic to click "Show More" until all papers are loaded or we find ours
        max_clicks = 5 # Avoid infinite loops
        clicks = 0
        
        while clicks < max_clicks:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Search for title in the current list
            # Links are in td.gsc_a_t > a
            papers = soup.select("td.gsc_a_t > a")
            
            # Normalize title for comparison (basic)
            target_title_clean = re.sub(r'\W+', '', paper_title.lower())
            
            found = False
            for paper in papers:
                found_title_clean = re.sub(r'\W+', '', paper.text.lower())
                # Check for substring or high similarity? Exact match first.
                if target_title_clean in found_title_clean or found_title_clean in target_title_clean:
                    citation_link = paper['href']
                    if not citation_link.startswith("http"):
                         citation_link = "https://scholar.google.com" + citation_link
                    logging.info(f"Found citation link: {citation_link}")
                    found = True
                    break
            
            if found:
                break

            # Not found, try to load more
            show_more_btn = None
            try:
                show_more_btn = driver.find_element(By.ID, "gsc_bpf_more")
                if show_more_btn.is_enabled() and "gsc_bpf_more_dis" not in show_more_btn.get_attribute("class"):
                    logging.info("Clicking 'Show More'...")
                    driver.execute_script("arguments[0].click();", show_more_btn)
                    time.sleep(2) # Wait for ajax
                    clicks += 1
                else:
                    break # Button disabled or not found
            except Exception:
                break # Element issue

        if not citation_link:
            logging.warning(f"Could not find paper '{paper_title}' in author profile.")

    except Exception as e:
        logging.error(f"Error extracting citation view: {e}")
    
    return citation_link, driver


def extract_citation_view_details(url: str, driver: uc.Chrome, proxy: Optional[str] = None, headless: bool = True, tor_restart_cmd: Optional[str] = None, min_wait: int = 5000, max_wait: int = 15000) -> Tuple[Dict[str, Any], uc.Chrome]:
    """
    Extracts detailed info from the Google Scholar Citation View page.
    Returns: (details_dict, driver)
    """
    details = {}
    try:
        logging.info(f"Extracting details from citation view: {url}")
        
        success, _, driver = safe_driver_get(driver, url, proxy, headless, tor_restart_cmd, min_wait, max_wait)
        if not success:
            return {}, driver

        soup = BeautifulSoup(driver.page_source, "html.parser")
        wait(min_wait, max_wait)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Title
        title_elem = soup.find("a", class_="gsc_oci_title_link")
        if not title_elem: # sometimes it's just a div
             title_elem = soup.find("div", id="gsc_oci_title")
        
        if title_elem:
            details['Title'] = title_elem.get_text(strip=True)
            
        # Abstract (Description)
        desc_elem = soup.find("div", id="gsc_oci_descr")
        if desc_elem:
            details['Abstract'] = desc_elem.get_text(strip=True)
            
        # Fields: Authors, Publication date, Journal, etc.
        # They are in pairs of .gsc_oci_field and .gsc_oci_value
        fields = soup.find_all("div", class_="gsc_oci_field")
        values = soup.find_all("div", class_="gsc_oci_value")
        
        field_map = {}
        for f, v in zip(fields, values):
            field_name = f.get_text(strip=True)
            field_value = v.get_text(strip=True)
            field_map[field_name] = field_value
            
        if 'Authors' in field_map:
            details['Authors'] = field_map['Authors']
            
        if 'Publication date' in field_map:
            # Try to extract year
            date_str = field_map['Publication date']
            year = extract_year(date_str)
            if year:
                details['Year'] = year
                
        # Construct Publication Info
        pub_info_parts = []
        if 'Journal' in field_map:
             pub_info_parts.append(field_map['Journal'])
        elif 'Source' in field_map:
             pub_info_parts.append(field_map['Source'])
        elif 'Conference' in field_map:
             pub_info_parts.append(field_map['Conference'])
        elif 'Book' in field_map:
             pub_info_parts.append(field_map['Book'])
             
        if 'Volume' in field_map:
            pub_info_parts.append(f"Vol. {field_map['Volume']}")
        if 'Issue' in field_map:
            pub_info_parts.append(f"Issue {field_map['Issue']}")
        if 'Pages' in field_map:
            pub_info_parts.append(f"pp. {field_map['Pages']}")
        if 'Publisher' in field_map:
            pub_info_parts.append(field_map['Publisher'])
            

        if pub_info_parts:
            details['Publication_Info'] = ", ".join(pub_info_parts)
            
        # Extract Side-Panel PDF Link (if available) -> div.gsc_oci_title_ggi a
        pdf_link_div = soup.find("div", class_="gsc_oci_title_ggi")
        if pdf_link_div:
            pdf_anchor = pdf_link_div.find("a")
            if pdf_anchor:
                pdf_url = pdf_anchor.get('href')
                if pdf_url:
                    details['Citation_View_PDF_Link'] = pdf_url
                    logging.info(f"Found PDF link in Citation View: {pdf_url}")
    except Exception as e:
        logging.error(f"Error extracting citation view details: {e}")
        
    return details, driver


def parse_search_result(job_element: Tag, current_page_index: int, order_in_page: int, scraped_links: set, driver: Optional[uc.Chrome] = None, proxy: Optional[str] = None, headless: bool = True, tor_restart_cmd: Optional[str] = None, min_wait: int = 5000, max_wait: int = 15000) -> Optional[Dict[str, Any]]:
    """Parses a single search result from a BeautifulSoup element."""
    links = job_element.find("a")
    if not links:
        return None

    link_url = links["href"]

    if link_url in scraped_links:
        logging.warning(f"Skipping already scraped link: {link_url}")
        return None

    title_element = links.text.strip()

    ref_element = job_element.find("div", class_="gs_a")
    ref_element_text = ref_element.text if ref_element else ""

    # Extract First Available Author Profile Link
    first_author_link = None
    if ref_element:
        # Iterate through all anchors to find the first one that looks like an author profile
        author_anchors = ref_element.find_all('a')
        for anchor in author_anchors:
            href = anchor.get('href', '')
            if 'user=' in href or '/citations' in href:
                first_author_link = href
                if not first_author_link.startswith("http"):
                    first_author_link = "https://scholar.google.com" + first_author_link
                break

    authors_part = ref_element_text.split(' - ')[0]
    publication_part = ' - '.join(ref_element_text.split(' - ')[1:]) if ' - ' in ref_element_text else ""

    year = extract_year(ref_element_text)

    abstract_element = job_element.find("div", class_="gs_rs")
    snippet = abstract_element.text.strip() if abstract_element else None
    
    # By default, abstract is the snippet unless we fetch details
    abstract = snippet

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
        'Snippet': snippet,
        'Link': link,
        'DOI': doi,
        'Citations': citations,
        'Scholar_Link': link_url,
        'Citation_Link': None,
        'First_Author_Link': first_author_link
    }


    
    if first_author_link:
        logging.info(f"Looking for citation view via author: {first_author_link}")
        # Call valid find_citation_view_url with safe args
        citation_view_url, driver = find_citation_view_url(first_author_link, title_element, driver, proxy, headless, tor_restart_cmd, min_wait, max_wait)
        
        if citation_view_url:
             entry_data['Citation_Link'] = citation_view_url
             # Now extract specific details from this view and overwrite/enhance
             citation_details, driver = extract_citation_view_details(citation_view_url, driver, proxy, headless, tor_restart_cmd, min_wait, max_wait)
             if citation_details:
                 logging.info("Overwriting/Enhancing data with Citation View details")
                 entry_data.update(citation_details)


    logging.info(f"Page: {current_page_index}, Order: {order_in_page}")
    logging.info(f"Title: {title_element}")
    logging.info(f"Year: {year}")
    logging.info(f"Authors: {authors_part}")
    logging.info(f"Publication Info: {publication_part}")
    logging.info(f"Abstract: {entry_data.get('Abstract', 'N/A')}")
    logging.info(f"Link: {link}")
    logging.info(f"DOI: {entry_data.get('DOI', 'N/A')}")
    logging.info(f"Citations: {citations}")
    logging.info(f"Author Keywords: {entry_data.get('Author_Keywords', 'N/A')}")
    logging.info("-" * 20)

    return entry_data


def load_existing_data(csv_file: str) -> pd.DataFrame:
    """Loads existing data from csv_file or creates a new DataFrame."""
    if os.path.exists(csv_file):
        logging.info(f"Found existing data in {csv_file}. Resuming scrape.")
        df = pd.read_csv(csv_file)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
    else:
        df = pd.DataFrame(columns=COLUMNS)
    return df


def save_data(df: pd.DataFrame, new_results: List[Dict[str, Any]], csv_file: str):
    """Saves new results to the CSV file."""
    if new_results:
        new_df = pd.DataFrame(new_results, columns=COLUMNS)
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(csv_file, index=False, quoting=csv.QUOTE_ALL)
        logging.info(f"Saved {len(new_results)} new results to {csv_file}")
    return df


def generate_bib_file(csv_file: str, bib_file: str):
    """Generates a .bib file from the scraped data."""
    if not os.path.exists(csv_file):
        return

    final_df = pd.read_csv(csv_file)
    if not final_df.empty:
        final_df['BibTeX'] = final_df.apply(generate_bibtex, axis=1)
        bibtex_entries = final_df['BibTeX'].dropna().tolist()
        if bibtex_entries:
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(bibtex_entries))
            logging.info(f"Successfully generated {bib_file} with {len(bibtex_entries)} entries.")


def scrape_page(page_num: int, base_url: str, scraped_links: set, proxy: Optional[str] = None, headless: bool = True, driver: Optional[uc.Chrome] = None, min_wait: int = 5000, max_wait: int = 15000, tor_restart_cmd: Optional[str] = None) -> Tuple[List[Dict[str, Any]], uc.Chrome, bool]:
    """Scrapes a single page of Google Scholar results."""
    driver_created_locally = False
    
    if driver is None:
        options = Options()
        if not headless:
             options.add_argument("--window-size=1920,1080")
        else:
             options.add_argument("--headless=new")

        if proxy:
             options.add_argument(f'--proxy-server={proxy}')
        
        with lock:
             # Force headless=False in uc init, handle headless via options
             driver = uc.Chrome(options=options, headless=False, version_main=144)
        driver_created_locally = True

    new_results = []
    current_page_index = page_num // 10 + 1
    
    # URL construction
    if 'start=' in base_url:
        current_url = re.sub(r'start=\d+', f'start={page_num}', base_url)
    else:
        current_url = f"{base_url}&start={page_num}"

    logging.info(f"Scraping page {current_page_index}")
    
    # Define validator for search page
    def validate_search_page(d: uc.Chrome) -> bool:
        s = BeautifulSoup(d.page_source, "html.parser")
        # Valid if results present OR explicit "no results" message
        if s.find("div", id="gs_res_ccl_mid"):
            return True
        txt = s.get_text().lower()
        if "did not match any articles" in txt or "no results found" in txt:
             return True
        return False

    # Use safe_driver_get for centralized block handling
    success, should_stop, driver = safe_driver_get(driver, current_url, proxy, headless, tor_restart_cmd, min_wait, max_wait, validator=validate_search_page)

    if not success:
        logging.error(f"Failed to scrape page {current_page_index} after retries.")
        if driver_created_locally and driver:
             try:
                 driver.quit()
             except:
                 pass
        return [], driver, False

    # Block detection is handled by safe_driver_get.
    
    # Now check for "No Results" specific to Search Results
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        results_container = soup.find("div", id="gs_res_ccl_mid")
        if not results_container:
            # Improved No Results vs Block detection
            page_text_lower = soup.get_text().lower()
            if "did not match any articles" in page_text_lower or "no results found" in page_text_lower:
                logging.warning(f"No results found on page {current_page_index}. Stopping.")
                if driver_created_locally and driver:
                     try: driver.quit()
                     except: pass
                return [], driver, True
            else:
                 logging.warning(f"Results container missing and no 'No Results' text on page {current_page_index}. Suspected silent block.")
                 if driver_created_locally and driver:
                     try: driver.quit()
                     except: pass
                 return [], driver, False

        job_elements = results_container.find_all("div", class_="gs_ri")
        if not job_elements:
            logging.warning(f"No results found on page {current_page_index}. Stopping.")
            if driver_created_locally and driver:
                 try: driver.quit()
                 except: pass
            return [], driver, True
        
        for i, job_element in enumerate(job_elements):
            try:
                 # Pass required args to parse_search_result 
                 res = parse_search_result(job_element, current_page_index, i+1, scraped_links, driver, proxy, headless, tor_restart_cmd, min_wait, max_wait)
                 if res:
                     new_results.append(res)
            except Exception as e:
                logging.error(f'Error parsing result {i+1} on page {current_page_index}: {e}')
                
        logging.info(f"Successfully scraped page {current_page_index}, found {len(new_results)} new results.")

    except Exception as e:
        logging.error(f"An error occurred while scraping page {current_page_index}: {e}")
    finally:
        if driver_created_locally and driver:
            try:
                driver.quit()
            except:
                pass
    
    return new_results, driver, False


def scrape_page_worker(driver_queue: queue.Queue, page_num: int, base_url: str, scraped_links: set, proxy: Optional[str], headless: bool, min_wait: int, max_wait: int, tor_restart_cmd: Optional[str]) -> Tuple[List[Dict[str, Any]], bool]:
    """Worker function to process a page using a driver from the pool."""
    driver = driver_queue.get()
    try:
        results, new_driver, should_stop = scrape_page(page_num, base_url, scraped_links, proxy, headless, driver, min_wait, max_wait, tor_restart_cmd)
        driver = new_driver # Update reference in case it was recreated
        return results, should_stop
    finally:
        driver_queue.put(driver)



def main():
    """Main function to run the Google Scholar scraper."""
    parser = argparse.ArgumentParser(description='Scrape Google Scholar search results.')
    parser.add_argument('url', nargs='?',
                        default='https://scholar.google.com/scholar?start=0&q=%22autism%22+and+%22bangladesh%22&hl=en&as_sdt=0,48&as_ylo=2020&as_yhi=2025&as_rr=1&as_vis=1',
                        help='The Google Scholar search URL to scrape.')
    parser.add_argument('--num-pages', type=int, default=100, help='Number of pages to scrape.')
    parser.add_argument('--max-workers', type=int, default=1, help='Maximum number of parallel workers. Default is 1 for safety.')
    parser.add_argument('--proxy', type=str, default='socks5://127.0.0.1:9050', help='Proxy server URL.')
    # Headless mode removed, always visible
    
    parser.add_argument('--start-page', type=int, help='Page number to start scraping from (1-based, overrides auto-resume).')
    parser.add_argument('--min-wait', type=int, default=100, help='Minimum milliseconds to wait between requests.')
    parser.add_argument('--max-wait', type=int, default=3000, help='Maximum milliseconds to wait between requests.')
    parser.add_argument('--tor-restart-cmd', type=str, help='Shell command to restart Tor service (e.g., "brew services restart tor").')
    parser.add_argument('--output', type=str, default='scrapped_gscholar', help='Output filename prefix (without extension). Default: scrapped_gscholar')
    args = parser.parse_args()
    
    # Auto-detect Tor restart command if not provided
    if not args.tor_restart_cmd:
        if sys.platform == "darwin":
            logging.info("Auto-detected macOS. Using 'brew services restart tor' as default Tor restart command.")
            args.tor_restart_cmd = "brew services restart tor"
        elif sys.platform == "linux":
             logging.info("Auto-detected Linux. Using 'sudo systemctl restart tor' as default Tor restart command.")
             args.tor_restart_cmd = "sudo systemctl restart tor"
    
    # Setup dynamic filenames
    csv_file = f"{args.output}.csv"
    bib_file = f"{args.output}.bib"
    log_file = f"{args.output}.log"
    
    setup_logging(log_file)
    
    # Check Tor connection if proxy is set
    if args.proxy:
        check_tor_connection(args.proxy)

    # Sanitize URL: remove backslashes that might be introduced by shell escaping
    base_url = args.url.replace('\\', '')

    headless = False # Always visible as per user request

    df = load_existing_data(csv_file)
    scraped_links = set(df['Scholar_Link'].dropna())

    start_page = 0
    if args.start_page:
        start_page = args.start_page - 1
        logging.info(f"Starting from page {args.start_page} (Manually specified)")
    elif not df.empty and 'Page_Index' in df.columns and df['Page_Index'].notna().any():
        last_page = df['Page_Index'].max()
        start_page = int(last_page)
        logging.info(f"Resuming scrape from page {start_page + 1}")
    else:
        match = re.search(r'start=(\d+)', base_url)
        if match:
            start_page = int(match.group(1)) // 10
    
    pages_to_scrape = [((start_page + i) * 10) for i in range(args.num_pages)]

    # Determine pool size
    # Don't create more drivers than pages needed
    pool_size = min(args.max_workers, len(pages_to_scrape))
    if pool_size < 1:
        pool_size = 1
    logging.info(f"Using driver pool size of {pool_size}.")

    # Initialize Driver Pool
    driver_queue = queue.Queue()
    drivers = []
    
    logging.info(f"Initializing {pool_size} browser(s)...")
    for _ in range(pool_size):
        options = Options()
        if not headless:
            options.add_argument("--window-size=1920,1080")
        else:
            options.add_argument("--headless=new")
            
        if args.proxy:
             options.add_argument(f'--proxy-server={args.proxy}')
        
        # Force headless=False in uc init, handle headless via options
        d = uc.Chrome(options=options, headless=False, version_main=144)
        drivers.append(d)

        driver_queue.put(d)

    try:
        # We enforce max_workers to match pool_size so tasks don't block waiting for drivers often
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            future_to_page = {
                executor.submit(
                    scrape_page_worker, 
                    driver_queue, 
                    page_num, 
                    base_url, 
                    scraped_links, 
                    args.proxy, 
                    headless, 
                    args.min_wait,
                    args.max_wait,
                    args.tor_restart_cmd
                ): page_num 
                for page_num in pages_to_scrape
            }
            
            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    results, should_stop = future.result()
                    if results:
                        # Incremental flush
                        df = save_data(df, results, csv_file)
                    
                    if should_stop:
                        logging.info(f"Stop signal received from page {page_num // 10 + 1}. Cancelling remaining tasks.")
                        for f in future_to_page:
                            f.cancel()
                        break

                except Exception as exc:
                    logging.error(f'Page {page_num // 10 + 1} generated an exception: {exc}')
    finally:
        logging.info("Closing all drivers in pool...")
        for d in drivers:
            try:
                d.quit()
            except Exception as e:
                logging.error(f"Error closing driver: {e}")

    # Sort the final CSV
    try:
        if os.path.exists(csv_file):
            logging.info("Sorting CSV file by Page and Order...")
            df = pd.read_csv(csv_file)
            if 'Page_Index' in df.columns and 'Order_in_Page' in df.columns:
                 df.sort_values(by=['Page_Index', 'Order_in_Page'], ascending=[True, True], inplace=True)
                 df.to_csv(csv_file, index=False)
                 logging.info("CSV file sorted.")
    except Exception as e:
        logging.error(f"Error sorting CSV: {e}")

    generate_bib_file(csv_file, bib_file)
    logging.info("Job finished, Godspeed you! Cite us.")


if __name__ == "__main__":
    main()