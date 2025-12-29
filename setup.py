from setuptools import setup, find_packages

setup(
    name='gscrapper',
    version='0.1.0',
    description='Google Scholar Scraper',
    author='Jules',
    packages=find_packages(),
    install_requires=[
        'undetected-chromedriver',
        'pandas',
        'beautifulsoup4',
        'selenium',
    ],
    entry_points={
        'console_scripts': [
            'gscrapper=gscrapper.cli:main',
        ],
    },
)
