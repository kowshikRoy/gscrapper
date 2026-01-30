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
    The script is configured to use `socks5://127.0.0.1:9050` as the default proxy.
    Simply run the script as usual:
    `python scrapper.py`

    If you need to use a different proxy address or port, use the `--proxy` argument (e.g. `--proxy socks5://127.0.0.1:9150`).

## Usage

To start scraping, run the script with a Google Scholar search URL. The browser will open in **visible mode** (non-headless) to improve stability and avoid detection.

```bash
python scrapper.py "your-google-scholar-url"
```

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `url` | The Google Scholar search URL to scrape. Should be quoted. | *Default internal URL* |
| `--output` | Output filename prefix (without extension). Generates `.csv`, `.bib`, and `.log` files. | `scrapped_gscholar` |
| `--num-pages` | Number of search result pages to scrape. | `100` |
| `--max-workers` | Maximum number of parallel browser instances. | `1` |
| `--start-page` | Manually specify the starting page number (1-based). Overrides auto-resume. | `None` |

### Examples

**Basic Usage:**
```bash
python scrapper.py --output "ml_results" --max-workers 2 "https://scholar.google.com/scholar?q=machine+learning"
```

**Custom Output Filename:**
```bash
# Creates my_results.csv, my_results.bib, my_results.log
python scrapper.py "https://scholar.google.com/scholar?q=autism" --output "my_results"
```

**Parallel Scraping with Tor:**
```bash
python scrapper.py "https://scholar.google.com/scholar?q=AI" --max-workers 2
```


### Solving CAPTCHAs

When you run the script, it may be interrupted by a CAPTCHA or "Unusual Traffic" block. The script will pause and prompt you to solve the CAPTCHA in the open browser window. Once you've solved it and the results are visible, press `Enter` in the terminal to continue scraping.

The scraped data will be saved to `[output].csv` (default: `scrapped_gscholar.csv`), and a corresponding BibTeX file will be generated at `[output].bib`.
