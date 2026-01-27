#!/usr/bin/env python3
"""
Process split PDFs as a single book.

1. Convert each split PDF to markdown via MinerU
2. Combine all markdown files into one full.md
3. Run the rest of the pipeline on the combined markdown
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for mineru_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from mineru_client import MineruClient
from pdf2skills.run_pipeline import (
    run_chunking,
    run_density_analysis,
    run_sku_extraction,
    run_knowledge_fusion,
    run_skill_generation,
    print_header,
    print_step,
    check_stage_complete,
)


def combine_markdown_files(markdown_files: list[Path], output_file: Path):
    """
    Combine multiple markdown files into one.
    
    Args:
        markdown_files: List of markdown file paths (sorted)
        output_file: Path to output combined markdown file
    """
    print(f"\nCombining {len(markdown_files)} markdown files...")
    
    combined_content = []
    
    for i, md_file in enumerate(markdown_files, 1):
        print(f"  Reading part {i}/{len(markdown_files)}: {md_file.name}")
        content = md_file.read_text(encoding='utf-8')
        
        # Add a separator between parts (except before first part)
        if i > 1:
            combined_content.append("\n\n---\n\n")
            combined_content.append(f"# Part {i}\n\n")
        
        combined_content.append(content)
    
    # Write combined content
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("".join(combined_content), encoding='utf-8')
    
    total_size = output_file.stat().st_size / 1024 / 1024
    print(f"  Combined markdown saved: {output_file} ({total_size:.1f} MB)")


def process_split_pdfs(
    split_pdfs: list[Path],
    output_dir: Path,
    language: str = "en",
    resume: bool = False
):
    """
    Process split PDFs as a single book.
    
    Args:
        split_pdfs: List of split PDF file paths (should be sorted)
        output_dir: Output directory for combined results
        language: PDF language for OCR ("ch" or "en")
        resume: Whether to resume from existing progress
    """
    start_time = datetime.now()
    
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print_header("pdf2skills - Split PDFs Pipeline")
    print(f"Split PDFs:  {len(split_pdfs)} files")
    print(f"Output Dir:  {output_dir}")
    print(f"Language:    {language}")
    print(f"Resume Mode: {resume}")
    print(f"Started:     {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    total_steps = 6
    results = {}
    
    # =========================================================================
    # Stage 1: Convert each split PDF to Markdown (MinerU)
    # =========================================================================
    print_step(1, total_steps, "PDF to Markdown (MinerU API) - Processing Splits")
    
    if resume and check_stage_complete(output_dir, "mineru"):
        print("  [SKIP] Already completed - full.md exists")
        results["mineru"] = "skipped"
        markdown_path = output_dir / "full.md"
    else:
        client = MineruClient(language=language)
        split_markdowns = []
        
        # Process each split
        for i, pdf_path in enumerate(split_pdfs, 1):
            print(f"\n  Processing split {i}/{len(split_pdfs)}: {pdf_path.name}")
            split_output = output_dir / f"split_{i:02d}_output"
            client.convert_pdf(pdf_path, split_output)
            
            # Find the markdown file in the output
            split_md = split_output / "full.md"
            if split_md.exists():
                split_markdowns.append(split_md)
            else:
                raise FileNotFoundError(f"Markdown not found in {split_output}")
        
        # Combine all markdown files
        print(f"\n  Combining {len(split_markdowns)} markdown files...")
        markdown_path = output_dir / "full.md"
        combine_markdown_files(split_markdowns, markdown_path)
        
        results["mineru"] = "complete"
    
    if not markdown_path.exists():
        raise FileNotFoundError(f"Combined markdown not found: {markdown_path}")
    
    # =========================================================================
    # Stage 2: Markdown → Chunks (Onion Peeler)
    # =========================================================================
    print_step(2, total_steps, "Markdown Chunking (Onion Peeler)")
    
    chunks_dir = output_dir / "full_chunks"
    if resume and check_stage_complete(output_dir, "chunks"):
        print("  [SKIP] Already completed - chunks_index.json exists")
        results["chunks"] = "skipped"
    else:
        run_chunking(markdown_path, output_dir)
        results["chunks"] = "complete"
    
    if not (chunks_dir / "chunks_index.json").exists():
        raise FileNotFoundError(f"Chunks not found: {chunks_dir}")
    
    # =========================================================================
    # Stage 3: Chunks → Density Scores (Semantic Density)
    # =========================================================================
    print_step(3, total_steps, "Semantic Density Analysis")
    
    density_dir = output_dir / "full_chunks_density"
    density_file = density_dir / "density_scores.json"
    
    if resume and check_stage_complete(output_dir, "density"):
        print("  [SKIP] Already completed - density_scores.json exists")
        results["density"] = "skipped"
    else:
        run_density_analysis(chunks_dir)
        results["density"] = "complete"
    
    if not density_file.exists():
        raise FileNotFoundError(f"Density scores not found: {density_file}")
    
    # =========================================================================
    # Stage 4: Chunks → SKUs (SKU Extractor)
    # =========================================================================
    print_step(4, total_steps, "SKU Extraction")
    
    skus_dir = output_dir / "full_chunks_skus"
    
    if resume and check_stage_complete(output_dir, "skus"):
        print("  [SKIP] Already completed - skus_index.json exists")
        results["skus"] = "skipped"
    else:
        run_sku_extraction(chunks_dir, density_file, skus_dir)
        results["skus"] = "complete"
    
    if not (skus_dir / "skus_index.json").exists():
        raise FileNotFoundError(f"SKUs not found: {skus_dir}")
    
    # =========================================================================
    # Stage 5: SKUs → Fused SKUs (Knowledge Fusion)
    # =========================================================================
    print_step(5, total_steps, "Knowledge Fusion")
    
    if resume and check_stage_complete(output_dir, "fusion"):
        print("  [SKIP] Already completed - buckets.json exists")
        results["fusion"] = "skipped"
    else:
        fusion_results = run_knowledge_fusion(skus_dir)
        results["fusion"] = fusion_results
    
    # =========================================================================
    # Stage 6: SKUs → Claude Skills (Skill Generator)
    # =========================================================================
    print_step(6, total_steps, "Skill Generation")
    
    skills_dir = skus_dir / "generated_skills"
    
    if resume and check_stage_complete(output_dir, "skills"):
        print("  [SKIP] Already completed - index.md exists")
        results["skills"] = "skipped"
    else:
        run_skill_generation(skus_dir, skills_dir)
        results["skills"] = "complete"
    
    # =========================================================================
    # Summary
    # =========================================================================
    end_time = datetime.now()
    duration = end_time - start_time
    
    print_header("Pipeline Complete!", "=")
    print(f"Duration: {duration}")
    print(f"\nResults:")
    for stage, status in results.items():
        if isinstance(status, dict):
            print(f"  {stage}: {status}")
        else:
            print(f"  {stage}: {status}")
    
    print(f"\nOutput structure:")
    print(f"  {output_dir}/")
    print(f"    ├── full.md                        (Combined Markdown)")
    print(f"    ├── split_*_output/                 (Individual split outputs)")
    print(f"    ├── full_chunks/                   (Chunked documents)")
    print(f"    ├── full_chunks_density/           (Density analysis)")
    print(f"    │   ├── density_scores.json")
    print(f"    │   └── heatmap.html")
    print(f"    └── full_chunks_skus/              (Knowledge units)")
    print(f"        ├── skus/                      (Individual SKUs)")
    print(f"        ├── buckets.json               (Grouped SKUs)")
    print(f"        └── generated_skills/          (Claude Skills)")
    print(f"            ├── index.md               (Skill index)")
    print(f"            └── <skill-name>/SKILL.md  (Individual skills)")
    
    print(f"\nGenerated skills are ready at:")
    print(f"  {skills_dir}")
    
    return output_dir


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Process split PDFs as a single book",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all splits in a directory
  python process_split_pdfs.py test_data/BaselFramework_splits/ --output-dir test_data/BaselFramework_output
  
  # Process specific split files
  python process_split_pdfs.py file1.pdf file2.pdf file3.pdf --output-dir combined_output
"""
    )
    
    parser.add_argument(
        "splits",
        nargs="+",
        help="Split PDF files or directory containing split PDFs"
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: <first_pdf_name>_output)"
    )
    parser.add_argument(
        "-l", "--language",
        choices=["ch", "en"],
        default="en",
        help="PDF language for OCR (default: en)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing progress"
    )
    
    args = parser.parse_args()
    
    # Collect split PDFs
    split_pdfs = []
    for item in args.splits:
        path = Path(item)
        if path.is_dir():
            # If it's a directory, find all PDFs and sort them
            pdfs = sorted(path.glob("*.pdf"))
            split_pdfs.extend(pdfs)
        elif path.is_file() and path.suffix.lower() == ".pdf":
            split_pdfs.append(path)
        else:
            print(f"Warning: Skipping {item} (not a PDF file or directory)")
    
    if not split_pdfs:
        print("Error: No PDF files found")
        sys.exit(1)
    
    # Sort to ensure correct order
    split_pdfs = sorted(split_pdfs)
    
    print(f"Found {len(split_pdfs)} split PDFs:")
    for i, pdf in enumerate(split_pdfs, 1):
        print(f"  {i}. {pdf.name}")
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # Use the first PDF's name (without _partXX)
        first_pdf = split_pdfs[0]
        base_name = first_pdf.stem
        # Remove _partXX suffix if present
        if "_part" in base_name:
            base_name = base_name.rsplit("_part", 1)[0]
        output_dir = first_pdf.parent / f"{base_name}_output"
    
    try:
        process_split_pdfs(
            split_pdfs=split_pdfs,
            output_dir=output_dir,
            language=args.language,
            resume=args.resume
        )
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        print("Use --resume to continue from where you left off.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        print("\nIf this is a rate limit error, wait a few minutes and run with --resume")
        raise


if __name__ == "__main__":
    main()
