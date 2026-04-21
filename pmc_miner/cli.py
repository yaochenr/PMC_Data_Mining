"""Unified command-line interface for pmc_miner.

Usage examples:
    pmc-miner search --output-dir results/ --max-papers 100
    pmc-miner doi    --input dois.csv --output-dir doi_results/ --paper-type molglue
    pmc-miner images --data-dir  results/filtered_papers
    pmc-miner image-summary --data-dir results/filtered_papers
"""

import argparse
from pathlib import Path

from pmc_miner.core.config import BATCH_SIZE, MAX_PAPERS
from pmc_miner.mining.doi_miner import DOIBasedMiner
from pmc_miner.mining.search_miner import SearchBasedMiner
from pmc_miner.utils.logging import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pmc-miner",
        description="Mine full-text papers from PMC Central.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Keyword-based mining with dual storage")
    s.add_argument("--output-dir", required=True, help="Root directory for mined data")
    s.add_argument("--max-papers", type=int, default=MAX_PAPERS)
    s.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    s.add_argument(
        "--init-dir-name",
        default="init_papers",
        help="Sub-directory inside --output-dir for ALL initially found papers",
    )
    s.add_argument(
        "--filtered-dir-name",
        default="filtered_papers",
        help="Sub-directory inside --output-dir for post-filtered papers",
    )
    s.add_argument(
        "--no-images",
        action="store_true",
        help="Skip figure image downloads (faster)",
    )
    s.add_argument(
        "--images-for",
        choices=["filtered", "init"],
        default="filtered",
        help="Download images only for filtered papers (default) or for every initial paper",
    )

    d = sub.add_parser("doi", help="DOI-based mining from a CSV of DOIs")
    d.add_argument("--input", required=True, help="CSV / text file of DOIs (one per line)")
    d.add_argument("--output-dir", required=True)
    d.add_argument(
        "--paper-type",
        default="generic",
        help="Label used in inventory/results filenames (e.g. molglue, protac)",
    )
    d.add_argument(
        "--no-images",
        action="store_true",
        help="Skip figure image downloads (faster)",
    )

    i = sub.add_parser("images", help="Download figures for all papers in a directory")
    i.add_argument("--data-dir", required=True, help="Directory containing PMC* sub-dirs")

    sm = sub.add_parser("image-summary", help="Print image-download stats for a data dir")
    sm.add_argument("--data-dir", required=True)

    return parser


def _run_search(args: argparse.Namespace) -> None:
    miner = SearchBasedMiner(
        output_dir=args.output_dir,
        init_dir_name=args.init_dir_name,
        filtered_dir_name=args.filtered_dir_name,
        download_images=not args.no_images,
        images_for=args.images_for,
    )
    miner.mine_papers(max_papers=args.max_papers, batch_size=args.batch_size)


def _run_doi(args: argparse.Namespace) -> None:
    miner = DOIBasedMiner(
        output_dir=args.output_dir,
        paper_type=args.paper_type,
        download_images=not args.no_images,
    )
    miner.mine_from_csv(args.input)


def _run_images(args: argparse.Namespace) -> None:
    from pmc_miner.core.storage import StorageManager
    from pmc_miner.utils.image_downloader import PMCImageDownloader

    storage = StorageManager(data_dir=Path(args.data_dir))
    PMCImageDownloader(storage).download_images_for_all_papers()


def _run_image_summary(args: argparse.Namespace) -> None:
    from pmc_miner.utils.image_summary import main as run_summary

    run_summary(args.data_dir)


def main() -> None:
    setup_logging()
    args = _build_parser().parse_args()
    {
        "search": _run_search,
        "doi": _run_doi,
        "images": _run_images,
        "image-summary": _run_image_summary,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
