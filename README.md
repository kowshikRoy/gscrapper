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

## Tor Proxy Setup

To use Tor proxy with this scrapper, follow these steps:

1.  **Install Tor:**
    *   **macOS:** `brew install tor`
    *   **Linux:** `sudo apt-get install tor` (Debian/Ubuntu) or `sudo dnf install tor` (Fedora)
    *   **Windows:** Download and install the Tor Browser, which includes a Tor client. You can also install Vidalia Bundle for a standalone Tor client.

2.  **Start Tor:**
    *   **macOS/Linux:** `brew services start tor` or `sudo systemctl start tor`
    *   **Windows:** The Tor Browser or Vidalia Bundle usually starts Tor automatically.

3.  **Verify Tor is running:**
    *   Check the Tor logs or status. On macOS/Linux, you can use `brew services list` or `sudo systemctl status tor`.
    *   The default SOCKS5 proxy address for Tor is `127.0.0.1:9050`.

4.  **Run the scrapper:**
    The script is already configured to use `socks5://127.0.0.1:9050` as the proxy.
    Simply run the script as usual:
    `python scrapper.py`

    If you need to use a different proxy address or port, modify the `--proxy-server` argument in `extract_paper_details` and `scrape_page` functions within `scrapper.py`.

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
