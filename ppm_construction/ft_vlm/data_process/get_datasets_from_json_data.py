#!/usr/bin/env python3
"""Process JSON circuit data and generate visualization datasets.

Reads JSONL from ppm_construction/data_syn/data/<note>.json,
compiles LaTeX to PDF, converts PDF to JPG, and generates labels.json.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add repo root to path for imports
script_path = Path(__file__).resolve()
repo_root = script_path.parent.parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from utils.dataprocess_utils import preprocess_latex, compile_latex, pdf2jpg

logger = logging.getLogger(__name__)


def compile_latex_codes(
    latex_codes: Dict[str, str],
    output_dir: Path,
    label_key: str = "spice"
) -> Dict[str, bool]:
    """Compile LaTeX codes to PDFs.
    
    Args:
        latex_codes: Dictionary mapping circuit IDs to LaTeX code
        output_dir: Directory to save PDFs
        label_key: Key to use in labels (default: "spice")
    
    Returns:
        Dictionary mapping circuit IDs to success status
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    
    for circuit_id, latex_code in latex_codes.items():
        try:
            processed_latex = preprocess_latex(latex_code)
            success = compile_latex(str(output_dir), circuit_id, processed_latex)
            results[circuit_id] = success
            if not success:
                logger.warning(f"Failed to compile LaTeX for circuit {circuit_id}")
        except Exception as e:
            logger.error(f"Error compiling LaTeX for circuit {circuit_id}: {e}")
            results[circuit_id] = False
    
    return results


def check_compiled_latex_codes(
    compiled_results: Dict[str, bool],
    output_dir: Path
) -> tuple[list[str], list[str]]:
    """Check which LaTeX codes were successfully compiled.
    
    Args:
        compiled_results: Dictionary from compile_latex_codes
        output_dir: Directory containing PDFs
    
    Returns:
        Tuple of (compiled_files, not_compiled_files) lists
    """
    compiled_files = []
    not_compiled_files = []
    
    for circuit_id, success in compiled_results.items():
        pdf_path = output_dir / f"{circuit_id}.pdf"
        if success and pdf_path.exists():
            compiled_files.append(circuit_id)
        else:
            not_compiled_files.append(circuit_id)
    
    return compiled_files, not_compiled_files


def make_datasets(
    data_file: Path,
    dataset_path: Path,
    label_key: str = "spice"
) -> None:
    """Process JSON data and create visualization dataset.
    
    Args:
        data_file: Path to input JSONL file
        dataset_path: Path to output dataset directory
        label_key: Key to use in labels.json (default: "spice")
    """
    dataset_path.mkdir(parents=True, exist_ok=True)
    
    # Read JSONL data
    logger.info(f"Reading circuit data from {data_file}")
    circuits_data = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    circuits_data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON line: {e}")
    
    logger.info(f"Loaded {len(circuits_data)} circuits")
    
    # Extract LaTeX codes
    latex_codes = {}
    circuit_metadata = {}
    for item in circuits_data:
        circuit_id = item.get("id")
        if not circuit_id:
            logger.warning("Skipping circuit without ID")
            continue
        
        latex_code = item.get("latex")
        if not latex_code:
            logger.warning(f"Skipping circuit {circuit_id} without LaTeX code")
            continue
        
        latex_codes[circuit_id] = latex_code
        circuit_metadata[circuit_id] = item
    
    # Compile LaTeX to PDF
    pdf_dir = dataset_path / "pdfs"
    logger.info(f"Compiling {len(latex_codes)} LaTeX files to PDFs...")
    compiled_results = compile_latex_codes(latex_codes, pdf_dir, label_key)
    
    # Check compilation results
    compiled_files, not_compiled_files = check_compiled_latex_codes(compiled_results, pdf_dir)
    logger.info(f"Successfully compiled {len(compiled_files)} PDFs, {len(not_compiled_files)} failed")
    
    # Convert PDFs to JPGs
    jpg_dir = dataset_path / "images"
    jpg_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Converting {len(compiled_files)} PDFs to JPGs...")
    converted_count = 0
    failed_count = 0
    
    for circuit_id in compiled_files:
        pdf_path = pdf_dir / f"{circuit_id}.pdf"
        jpg_path = jpg_dir / f"{circuit_id}.jpg"
        
        try:
            success = pdf2jpg(str(pdf_path), str(jpg_path), zoom_x=2, zoom_y=2)
            if success:
                converted_count += 1
            else:
                failed_count += 1
                logger.warning(f"Failed to convert PDF to JPG for circuit {circuit_id}")
        except Exception as e:
            failed_count += 1
            logger.error(f"Error converting PDF to JPG for circuit {circuit_id}: {e}")
    
    logger.info(f"Converted {converted_count} JPGs, {failed_count} failed")
    
    # Generate labels.json
    labels = {}
    for circuit_id in compiled_files:
        if circuit_id in circuit_metadata:
            metadata = circuit_metadata[circuit_id]
            labels[circuit_id] = {
                "image": f"images/{circuit_id}.jpg",
                label_key: metadata.get(label_key, ""),
                "latex": metadata.get("latex", ""),
                "stat": metadata.get("stat", {})
            }
    
    labels_file = dataset_path / "labels.json"
    with open(labels_file, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Generated labels.json with {len(labels)} entries")
    logger.info(f"Dataset saved to {dataset_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Process circuit JSON data and generate visualization dataset")
    parser.add_argument("--note", type=str, required=True, help="Dataset note/name")
    parser.add_argument("--label_key", type=str, default="spice", help="Key to use in labels.json (default: spice)")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Determine paths
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent.parent.parent
    
    data_file = repo_root / "ppm_construction" / "data_syn" / "data" / f"{args.note}.json"
    dataset_path = repo_root / "datasets" / args.note
    
    if not data_file.exists():
        logger.error(f"Data file not found: {data_file}")
        return 1
    
    make_datasets(data_file, dataset_path, label_key=args.label_key)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

