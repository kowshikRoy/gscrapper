# Project Context and Design

## Overview

This project is a web scraper designed to extract data from Google Scholar search results. The primary goal is to automate the collection of academic references for meta-analysis and literature reviews.

## Key Features

-   **Scrapes Google Scholar:** Extracts titles, authors, publication information, abstracts, and citation counts.
-   **Data Storage:** Saves scraped data to a CSV file (`scrapped_gscholar.csv`) and generates a BibTeX file (`scrapped_gscholar.bib`).
-   **Resumes Scraping:** The script is designed to resume from the last scraped page to avoid redundant requests.
-   **Anonymous Scraping:** Uses Tor to route traffic and `undetected-chromedriver` to prevent bot detection, minimizing CAPTCHA interruptions.

## Technical Design

-   **Language:** Python 3
-   **Libraries:**
    -   `selenium`: For browser automation.
    -   `undetected-chromedriver`: To avoid bot detection.
    -   `pandas`: For data manipulation and storage.
    -   `beautifulsoup4`: For parsing HTML.
-   **Proxy:** The script is configured to use the Tor network via a SOCKS5 proxy on `127.0.0.1:9050`.

## Troubleshooting History

### 1. `distutils` Dependency Issue

-   **Problem:** The script failed with a `ModuleNotFoundError` for `distutils` after switching to `undetected-chromedriver`. This is a known issue with Python 3.12, where `distutils` has been deprecated.
-   **Solution:** The issue was resolved by installing the `setuptools` library, which provides the necessary `distutils` components.

### 2. SSL Certificate Verification Error

-   **Problem:** The script encountered an `SSLCertVerificationError`, which prevented `undetected-chromedriver` from downloading the necessary driver. This is often caused by network restrictions or outdated root certificates.
-   **Solution:** A workaround was implemented by adding the following lines to the script to bypass SSL verification:
    ```python
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    ```

### 3. `FileNotFoundError` for `chromedriver`

-   **Problem:** The script failed with a `FileNotFoundError` because it was explicitly looking for the `chromedriver` executable at a hardcoded path.
-   **Solution:** The `driver_executable_path` and `headless` arguments were removed from the `uc.Chrome()` constructor to allow `undetected-chromedriver` to manage the driver automatically. The script was also made fully autonomous by removing the `input()` call.
