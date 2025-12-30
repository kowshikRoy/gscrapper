import pytest
import pandas as pd
from bs4 import BeautifulSoup
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import scrapper
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gscrapper.cli import (
    extract_year,
    extract_citations,
    generate_bibtex,
    parse_search_result,
    load_existing_data,
    COLUMNS
)

# --- Test Helper Functions ---

def test_extract_year():
    assert extract_year("Title (2023) - Author") == 2023
    assert extract_year("No year here") is None
    assert extract_year("Multiple years 2021 and 2022") == 2021 # Should get the first one

def test_extract_citations():
    # Helper to create a soup element
    def create_element(html):
        return BeautifulSoup(html, "html.parser")

    # Case 1: Citations present
    html_with_citations = '<div class="gs_fl"><a href="/scholar?cites=123">Cited by 50</a></div>'
    element = create_element(html_with_citations)
    assert extract_citations(element) == 50

    # Case 2: No citations link
    html_no_citations = '<div class="gs_fl"><a href="/related">Related articles</a></div>'
    element = create_element(html_no_citations)
    assert extract_citations(element) is None

    # Case 3: None element
    assert extract_citations(None) is None

def test_generate_bibtex():
    # Test case 1: Complete data
    entry = pd.Series({
        'Authors': 'Doe, John',
        'Year': 2023,
        'Title': 'Analysis of Everything',
        'Publication_Info': 'Journal of Science',
        'DOI': '10.1234/5678',
        'Abstract': 'This is an abstract.'
    })
    bibtex = generate_bibtex(entry)
    assert "@article{Doe2023Analysis," in bibtex
    assert "title={Analysis of Everything}," in bibtex
    assert "author={Doe, John}," in bibtex
    assert "year={2023}," in bibtex
    assert "doi={10.1234/5678}," in bibtex

    # Test case 2: Minimal data (error handling)
    entry_minimal = pd.Series({
        'Title': 'Minimal Title'
    })
    bibtex_minimal = generate_bibtex(entry_minimal)
    assert "@article{" in bibtex_minimal
    assert "title={Minimal Title}," in bibtex_minimal

def test_load_existing_data(tmp_path):
    # Patch the CSV_FILE constant in scrapper module
    with patch('gscrapper.cli.CSV_FILE', str(tmp_path / "test_data.csv")):
        # Case 1: File doesn't exist
        df = load_existing_data()
        assert df.empty
        assert list(df.columns) == COLUMNS

        # Case 2: File exists
        test_data = pd.DataFrame({'Title': ['Test Paper'], 'Page_Index': [1]})
        test_data.to_csv(tmp_path / "test_data.csv", index=False)

        df_loaded = load_existing_data()
        assert not df_loaded.empty
        assert len(df_loaded) == 1
        assert df_loaded.iloc[0]['Title'] == 'Test Paper'
        # Check if missing columns were added
        assert 'DOI' in df_loaded.columns

# --- Test Parsing Logic ---

def test_parse_search_result():
    html_template = """
    <div class="gs_ri">
        <h3 class="gs_rt"><a href="http://example.com/paper.pdf">Test Paper Title</a></h3>
        <div class="gs_a">Author Name - Journal Name, 2023 - Publisher</div>
        <div class="gs_rs">This is the abstract text.</div>
        <div class="gs_fl"><a href="/scholar?cites=10">Cited by 10</a></div>
    </div>
    """
    soup = BeautifulSoup(html_template, "html.parser")
    job_element = soup.find("div", class_="gs_ri")

    # Mock extract_paper_details to avoid network calls
    with patch('gscrapper.cli.extract_paper_details') as mock_details:
        mock_details.return_value = {'Abstract': 'Detailed Abstract', 'DOI': '10.1000/xyz'}

        result = parse_search_result(
            job_element=job_element,
            current_page_index=1,
            order_in_page=1,
            scraped_links=set()
        )

        assert result is not None
        assert result['Title'] == "Test Paper Title"
        assert result['Year'] == 2023
        assert result['Authors'] == "Author Name"
        assert result['Citations'] == 10
        assert result['Link'] == "http://example.com/paper.pdf"
        assert result['DOI'] == "10.1000/xyz"

def test_parse_search_result_skip_existing():
    html = '<div class="gs_ri"><h3><a href="http://exists.com">Title</a></h3></div>'
    soup = BeautifulSoup(html, "html.parser")
    job_element = soup.find("div", class_="gs_ri")

    result = parse_search_result(
        job_element=job_element,
        current_page_index=1,
        order_in_page=1,
        scraped_links={"http://exists.com"}
    )
    assert result is None
