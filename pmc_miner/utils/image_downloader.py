"""Image downloader for PMC papers, scrapes the HTML rendering since XML rarely has URLs."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from pmc_miner.core.storage import StorageManager


class PMCImageDownloader:
    """Downloads figure images from the PMC HTML page (XML rarely carries URLs)."""

    def __init__(self, storage_manager: StorageManager):
        self.storage = storage_manager
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def get_pmc_html_url(self, pmcid: str) -> str:
        clean_id = pmcid.replace('PMC', '')
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{clean_id}/"

    def scrape_figure_images(self, pmcid: str) -> List[Dict[str, str]]:
        try:
            url = self.get_pmc_html_url(pmcid)
            logging.info(f"Scraping images from: {url}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            figures = []

            img_tags = soup.find_all('img', src=True)
            logging.info(f"Found {len(img_tags)} total img tags")

            for img in img_tags:
                src = img.get('src', '')
                if not src:
                    continue

                if any(skip in src.lower() for skip in ['logo', 'icon', 'button', 'banner']):
                    continue

                is_figure = any(term in src.lower() for term in ['fig', 'image', 'graphic', 'bin/']) or \
                           any(term in (img.get('alt', '') + img.get('title', '')).lower() for term in ['fig', 'figure'])

                if not is_figure:
                    continue

                figure_id = ""
                caption = ""
                alt_text = img.get('alt', '')

                parent_fig = img.find_parent(['figure', 'div', 'section'])

                if parent_fig:
                    figure_id = parent_fig.get('id', '')
                    if not figure_id and parent_fig.get('class'):
                        figure_id = ' '.join(parent_fig.get('class', []))

                    caption_elem = parent_fig.find(['figcaption', 'div', 'p', 'span'])
                    if caption_elem and any(term in caption_elem.get_text().lower() for term in ['figure', 'fig']):
                        caption = caption_elem.get_text(strip=True)

                if src.startswith('//'):
                    src = 'https:' + src
                elif not src.startswith('http'):
                    src = urljoin(url, src)

                figures.append({
                    'id': figure_id or f"img_{len(figures)+1}",
                    'caption': caption[:500] if caption else alt_text[:500],
                    'image_url': src,
                    'alt_text': alt_text
                })

            seen_urls = set()
            unique_figures = []
            for fig in figures:
                if fig['image_url'] not in seen_urls:
                    seen_urls.add(fig['image_url'])
                    unique_figures.append(fig)

            logging.info(f"Found {len(unique_figures)} unique figure images for {pmcid}")
            return unique_figures

        except Exception as e:
            logging.error(f"Failed to scrape images for {pmcid}: {e}")
            return []

    def download_paper_images(self, pmcid: str) -> bool:
        try:
            figures = self.scrape_figure_images(pmcid)
            if not figures:
                logging.info(f"No figures found for PMC{pmcid}")
                return True

            paper_dir = self.storage.get_paper_dir(pmcid)
            images_dir = paper_dir / "images"
            images_dir.mkdir(exist_ok=True)

            downloaded_figures = []

            for i, figure in enumerate(figures):
                image_url = figure['image_url']
                figure_id = figure.get('id') or f"figure_{i+1}"

                parsed_url = urlparse(image_url)
                original_filename = Path(parsed_url.path).name

                if '.' in original_filename:
                    filename = f"{figure_id}_{original_filename}"
                else:
                    ext = '.jpg'
                    if 'png' in image_url.lower():
                        ext = '.png'
                    elif 'gif' in image_url.lower():
                        ext = '.gif'
                    elif 'tif' in image_url.lower():
                        ext = '.tif'
                    filename = f"{figure_id}{ext}"

                try:
                    response = self.session.get(image_url, stream=True, timeout=30)
                    response.raise_for_status()

                    image_path = images_dir / filename
                    with open(image_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    figure_with_path = figure.copy()
                    figure_with_path['local_image_path'] = f"images/{filename}"
                    downloaded_figures.append(figure_with_path)

                    logging.info(f"Downloaded: {filename}")
                    time.sleep(0.5)  # Be polite to NCBI.

                except Exception as e:
                    logging.warning(f"Failed to download {image_url}: {e}")
                    downloaded_figures.append(figure)

            figures_metadata_path = images_dir / "figures_metadata.json"
            with open(figures_metadata_path, 'w', encoding='utf-8') as f:
                json.dump(downloaded_figures, f, indent=2, ensure_ascii=False)

            logging.info(f"Downloaded {len([f for f in downloaded_figures if 'local_image_path' in f])} images for PMC{pmcid}")
            return True

        except Exception as e:
            logging.error(f"Failed to download images for PMC{pmcid}: {e}")
            return False

    def download_images_for_all_papers(self) -> Dict[str, bool]:
        all_papers = self.storage.get_all_paper_ids()
        results = {}

        logging.info(f"Starting image download for {len(all_papers)} papers...")

        for i, pmcid in enumerate(all_papers, 1):
            logging.info(f"Processing {pmcid} ({i}/{len(all_papers)})")

            paper_dir = self.storage.get_paper_dir(pmcid)
            images_dir = paper_dir / "images"
            if images_dir.exists() and any(images_dir.iterdir()):
                logging.info(f"Images already exist for {pmcid}, skipping")
                results[pmcid] = True
                continue

            success = self.download_paper_images(pmcid)
            results[pmcid] = success

            time.sleep(1)

        success_count = sum(results.values())
        logging.info(f"Image download complete: {success_count}/{len(all_papers)} papers successful")

        return results
