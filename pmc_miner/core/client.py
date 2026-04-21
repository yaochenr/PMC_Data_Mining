"""PMC API client for searching and retrieving papers."""

import logging
import time
from typing import Dict, List, Optional

import requests

from pmc_miner.core.config import (
    NCBI_BASE_URL, PMC_OA_SERVICE_URL, PMC_EFETCH_URL, RATE_LIMIT_DELAY, MAX_RETRIES,
    MOLECULAR_GLUE_KEYWORDS
)


class PMCClient:
    """Client for NCBI E-utilities against PMC."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PMC-Molecular-Glue-Miner/1.0 (research@example.com)'
        })

    def _rate_limit(self):
        time.sleep(RATE_LIMIT_DELAY)

    def _make_request(self, url: str, params: Dict = None) -> requests.Response:
        self._rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logging.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(2 ** attempt)

    def search_papers(self, keywords: List[str], max_results: int = 100) -> List[str]:
        query_parts = []
        for keyword in keywords:
            query_parts.append(f'"{keyword}"[Title/Abstract] OR "{keyword}"[Full Text]')

        search_query = " OR ".join(query_parts)

        open_access_filters = [
            '"open access"[filter]',
            '"free full text"[filter]',
            '"loatcfree full text"[sb]'
        ]
        oa_filter = " OR ".join(open_access_filters)
        search_query += f' AND ({oa_filter})'

        params = {
            'db': 'pmc',
            'term': search_query,
            'retmax': max_results,
            'retmode': 'json',
            'sort': 'relevance',
            'tool': 'PMC-Molecular-Glue-Miner',
            'email': 'research@example.com'
        }

        url = f"{NCBI_BASE_URL}/esearch.fcgi"

        try:
            response = self._make_request(url, params)
            data = response.json()

            if 'esearchresult' in data and 'idlist' in data['esearchresult']:
                pmc_ids = data['esearchresult']['idlist']
                logging.info(f"Found {len(pmc_ids)} papers in PMC Open Access subset")
                return pmc_ids
            else:
                logging.warning("No results found or unexpected response format")
                return []

        except Exception as e:
            logging.error(f"Search failed: {e}")
            return []

    def get_paper_metadata(self, pmc_ids: List[str]) -> List[Dict]:
        if not pmc_ids:
            return []

        batch_size = 100
        all_metadata = []

        for i in range(0, len(pmc_ids), batch_size):
            batch_ids = pmc_ids[i:i + batch_size]
            # ESummary 只接受不带 PMC 前缀的纯数字 ID。
            numeric_ids = [pid.replace('PMC', '') for pid in batch_ids]
            id_list = ",".join(numeric_ids)

            params = {
                'db': 'pmc',
                'id': id_list,
                'retmode': 'json',
                'tool': 'PMC-Molecular-Glue-Miner',
                'email': 'research@example.com'
            }

            url = f"{NCBI_BASE_URL}/esummary.fcgi"

            try:
                response = self._make_request(url, params)
                data = response.json()

                if 'result' in data:
                    for i, pmc_id in enumerate(batch_ids):
                        numeric_id = numeric_ids[i]
                        if numeric_id in data['result']:
                            metadata = data['result'][numeric_id]
                            all_metadata.append({
                                'pmcid': f"PMC{numeric_id}",
                                'title': metadata.get('title', ''),
                                'authors': metadata.get('authors', []),
                                'journal': metadata.get('fulljournalname', ''),
                                'pubdate': metadata.get('pubdate', ''),
                                'doi': metadata.get('doi', ''),
                                'pmid': metadata.get('pmid', '')
                            })

            except Exception as e:
                logging.error(f"Failed to get metadata for batch: {e}")

        logging.info(f"Retrieved metadata for {len(all_metadata)} papers")
        return all_metadata

    def get_full_text_xml(self, pmc_id: str) -> Optional[str]:
        if not pmc_id.startswith('PMC'):
            pmc_id = f'PMC{pmc_id}'

        params = {
            'db': 'pmc',
            'id': pmc_id,
            'rettype': 'xml',
            'retmode': 'text',
            'tool': 'PMC-Molecular-Glue-Miner',
            'email': 'research@example.com'
        }

        try:
            response = self._make_request(PMC_EFETCH_URL, params)
            if response.status_code == 200:
                xml_content = response.text

                if xml_content and len(xml_content) > 100:
                    if ('<article' in xml_content or '<pmc-articleset' in xml_content or
                        '<?xml' in xml_content[:100]):

                        if not any(error in xml_content.lower()[:500] for error in
                                 ['error', 'not found', 'unavailable', 'forbidden']):
                            logging.info(f"Successfully retrieved XML for {pmc_id}")
                            return xml_content
                        else:
                            logging.warning(f"{pmc_id}: XML contains error messages")
                    else:
                        logging.warning(f"{pmc_id}: Retrieved content doesn't appear to be valid XML")
                else:
                    logging.warning(f"{pmc_id}: Received empty or very short response")

        except Exception as e:
            logging.error(f"Failed to get full text for {pmc_id}: {e}")

        return None

    def search_and_collect(self, max_papers: int = 50) -> Dict:
        logging.info(f"Starting search for molecular glue papers (max: {max_papers})")

        pmc_ids = self.search_papers(MOLECULAR_GLUE_KEYWORDS, max_papers)

        if not pmc_ids:
            return {"papers": [], "total_found": 0}

        metadata = self.get_paper_metadata(pmc_ids)

        if len(metadata) > max_papers:
            metadata = metadata[:max_papers]

        return {
            "papers": metadata,
            "total_found": len(pmc_ids),
            "collected": len(metadata),
            "search_keywords": MOLECULAR_GLUE_KEYWORDS
        }

    def doi_to_pmcid(self, doi: str) -> Optional[str]:
        try:
            # 先只在 Open Access 子集里查,确保拿到的 PMC ID 有可下载的全文 XML。
            search_query = f'"{doi}"[DOI] AND ("open access"[filter] OR "free full text"[filter])'
            params = {
                'db': 'pmc',
                'term': search_query,
                'retmax': 1,
                'retmode': 'json',
                'tool': 'PMC-Molecular-Glue-Miner',
                'email': 'research@example.com'
            }

            url = f"{NCBI_BASE_URL}/esearch.fcgi"
            response = self._make_request(url, params)
            data = response.json()

            if 'esearchresult' in data and 'idlist' in data['esearchresult']:
                pmc_ids = data['esearchresult']['idlist']
                if pmc_ids:
                    pmc_id = f"PMC{pmc_ids[0]}"
                    logging.info(f"Found PMC ID {pmc_id} for DOI {doi} (Open Access)")
                    return pmc_id

            # 兜底:无 OA 过滤再查一次 (结果可能没有全文 XML)。
            search_query = f'"{doi}"[DOI]'
            params = {
                'db': 'pmc',
                'term': search_query,
                'retmax': 1,
                'retmode': 'json',
                'tool': 'PMC-Molecular-Glue-Miner',
                'email': 'research@example.com'
            }

            url = f"{NCBI_BASE_URL}/esearch.fcgi"
            response = self._make_request(url, params)
            data = response.json()

            if 'esearchresult' in data and 'idlist' in data['esearchresult']:
                pmc_ids = data['esearchresult']['idlist']
                if pmc_ids:
                    pmc_id = f"PMC{pmc_ids[0]}"
                    logging.info(f"Found PMC ID {pmc_id} for DOI {doi}")
                    return pmc_id
                else:
                    logging.warning(f"No PMC ID found for DOI {doi}")
                    return None
            else:
                logging.warning(f"No search results for DOI {doi}")
                return None

        except Exception as e:
            logging.error(f"Failed to convert DOI {doi} to PMC ID: {e}")
            return None

    @staticmethod
    def validate_full_text_availability(xml_content: str) -> bool:
        if not xml_content:
            return False

        restriction_indicators = [
            "publisher of this article does not allow downloading of the full text",
            "full text in XML form is not available",
            "only the abstract is available"
        ]

        xml_lower = xml_content.lower()
        for indicator in restriction_indicators:
            if indicator in xml_lower:
                return False

        body_indicators = [
            "<body>",
            "<sec",
            "<section",
            "<p>",
            "</body>"
        ]

        for indicator in body_indicators:
            if indicator in xml_lower:
                return True

        return False
