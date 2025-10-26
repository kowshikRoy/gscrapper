# Google Scholar Scraper

This script scrapes search results from Google Scholar, extracting titles, authors, publication information, and other relevant data. It's designed to assist with meta-analysis and literature reviews by automating the process of gathering academic references.

## Features

- Scrapes Google Scholar search results pages.
- Extracts title, year, authors, publication info, abstract, and citation count.
- Saves results to a CSV file (`scrapped_gscholar.csv`).
- Generates a BibTeX file (`scrapped_gscholar.bib`) for easy citation management.
- Resumes scraping from the last saved point.
- Handles CAPTCHAs by pausing and waiting for user input.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd gscrapper
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

To start scraping, run the script with a Google Scholar search URL. If no URL is provided, it will use a default example URL.

```bash
python scrapper.py "your-google-scholar-url"
```

### Example

```bash
python scrapper.py "https://scholar.google.com/scholar?q=machine+learning&hl=en&as_sdt=0,5"
```

When you run the script for the first time, it may be interrupted by a CAPTCHA. The script will pause and prompt you to solve the CAPTCHA in the browser window that it opens. Once you've solved it, press `Enter` in the terminal to continue scraping.

The scraped data will be saved to `scrapped_gscholar.csv`, and a corresponding BibTeX file will be generated at `scrapped_gscholar.bib`.
