"""pmc_miner — mine full-text papers, tables, figures, and supplementary files from PMC."""

from pmc_miner.core.client import PMCClient
from pmc_miner.core.models import (
    PaperInventory,
    PaperMetadata,
    PaperRecord,
    ProcessedPaper,
)
from pmc_miner.core.processor import TextProcessor
from pmc_miner.core.storage import StorageManager
from pmc_miner.core.supplementary_downloader import SupplementaryDownloader
from pmc_miner.mining.doi_miner import DOIBasedMiner
from pmc_miner.mining.search_miner import PostFilter, SearchBasedMiner
from pmc_miner.utils.image_downloader import PMCImageDownloader

__version__ = "0.2.0"

__all__ = [
    "SearchBasedMiner",
    "DOIBasedMiner",
    "PostFilter",
    "PMCClient",
    "TextProcessor",
    "StorageManager",
    "SupplementaryDownloader",
    "PMCImageDownloader",
    "PaperMetadata",
    "ProcessedPaper",
    "PaperRecord",
    "PaperInventory",
    "__version__",
]
