#!/usr/bin/env python3
"""
pdf2skills - Full Pipeline Runner

End-to-end pipeline for converting PDF books to Claude Code Skills.

Pipeline stages:
1. PDF → Markdown (MinerU API)
2. Markdown → Chunks (Onion Peeler)
3. Chunks → Density Scores (Semantic Density Analyzer)
4. Chunks → SKUs (SKU Extractor)
5. SKUs → Fused SKUs (Knowledge Fusion)
6. Fused SKUs → Claude Skills (Skill Generator)
7. All Outputs → Router (Router Generator)
8. SKUs → Glossary (Glossary Extractor)

Usage:
    python run_pipeline.py <pdf_path> [--output-dir <dir>] [--language <ch|en>]
    python run_pipeline.py --resume <output_dir>  # Resume from existing progress
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path for mineru_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


def print_header(title: str, char: str = "="):
    """Print a formatted section header."""
    width = 70
    print(f"\n{char * width}")
    print(f" {title}")
    print(f"{char * width}\n")


def print_step(step_num: int, total: int, title: str):
    """Print a step indicator."""
    print(f"\n[Step {step_num}/{total}] {title}")
    print("-" * 50)


def check_stage_complete(output_dir: Path, stage: str) -> bool:
    """Check if a pipeline stage has already completed."""
    markers = {
        "mineru": output_dir / "full.md",
        "chunks": output_dir / "full_chunks" / "chunks_index.json",
        "density": output_dir / "full_chunks_density" / "density_scores.json",
        "skus": output_dir / "full_chunks_skus" / "skus_index.json",
        "fusion": output_dir / "full_chunks_skus" / "buckets.json",
        "skills": output_dir / "full_chunks_skus" / "generated_skills" / "index.md",
        "router": output_dir / "full_chunks_skus" / "router.json",
        "glossary": output_dir / "full_chunks_skus" / "glossary.json",
    }
    return markers.get(stage, Path("")).exists()


def run_mineru(pdf_path: Path, output_dir: Path, language: str = "ch") -> Path:
    """Stage 1: Convert PDF to Markdown using MinerU API."""
    from mineru_client import MineruClient

    client = MineruClient(language=language)
    return client.convert_pdf(pdf_path, output_dir)


def run_chunking(markdown_path: Path, output_dir: Path) -> Path:
    """Stage 2: Chunk markdown using Onion Peeler."""
    from onion_peeler import OnionPeeler

    peeler = OnionPeeler(str(markdown_path))
    chunks_dir = output_dir / "full_chunks"
    return peeler.save_results(str(chunks_dir))


def run_density_analysis(chunks_dir: Path) -> Path:
    """Stage 3: Calculate semantic density scores."""
    from semantic_density import SemanticDensityAnalyzer

    analyzer = SemanticDensityAnalyzer(str(chunks_dir))
    return analyzer.save_results()


def run_sku_extraction(chunks_dir: Path, density_file: Path, output_dir: Path) -> Path:
    """Stage 4: Extract SKUs from chunks."""
    from sku_extractor import SKUExtractor

    extractor = SKUExtractor(
        chunks_dir=str(chunks_dir),
        density_file=str(density_file),
        output_dir=str(output_dir)
    )
    extractor.extract_all()
    extractor.save_results()
    return output_dir


def run_knowledge_fusion(skus_dir: Path) -> dict:
    """Stage 5: Run knowledge fusion pipeline."""
    from knowledge_fusion import (
        TagNormalizer,
        SKUBucketer,
        SimilarityCalculator,
        StateMatrix,
        SKUResolver
    )

    results = {}

    # 5.1 Tag Normalization
    print("\n  5.1 Tag Normalization...")
    normalizer = TagNormalizer(str(skus_dir))
    normalizer.normalize()
    results["normalization"] = "complete"

    # 5.2 SKU Bucketing
    print("\n  5.2 SKU Bucketing...")
    bucketer = SKUBucketer(str(skus_dir))
    bucketer.bucket()
    results["bucketing"] = "complete"

    # 5.3 Similarity Calculation
    print("\n  5.3 Similarity Calculation...")
    calculator = SimilarityCalculator(str(skus_dir))
    calculator.calculate()
    results["similarity"] = "complete"

    # 5.4 State Matrix (optional - only if duplicates/conflicts found)
    similarities_file = skus_dir / "similarities.json"
    if similarities_file.exists():
        import json
        with open(similarities_file) as f:
            sim_data = json.load(f)

        has_duplicates = len(sim_data.get("duplicates", [])) > 0
        has_conflicts = len(sim_data.get("conflicts", [])) > 0

        if has_duplicates or has_conflicts:
            print("\n  5.4 State Matrix & Resolution...")
            matrix = StateMatrix(str(skus_dir))
            matrix.build()

            resolver = SKUResolver(str(skus_dir))
            resolver.resolve()
            results["resolution"] = "complete"
        else:
            print("\n  5.4 Skipping resolution (no duplicates/conflicts)")
            results["resolution"] = "skipped"

    return results


def run_skill_generation(skus_dir: Path, output_dir: Path = None) -> Path:
    """Stage 6: Generate Claude Code Skills from SKUs."""
    from skill_generator import SkillGenerator

    if output_dir is None:
        output_dir = skus_dir / "generated_skills"

    generator = SkillGenerator(str(skus_dir), str(output_dir))
    generator.generate_all()
    generator.package_skills()

    return output_dir


def run_router_generation(output_dir: Path) -> Path:
    """Stage 7: Generate hierarchical router from all outputs."""
    from router_generator import RouterGenerator

    generator = RouterGenerator(str(output_dir))
    generator.generate()
    return generator.save_results()


def run_glossary_extraction(output_dir: Path, use_llm: bool = False) -> Path:
    """Stage 8: Extract domain glossary from SKUs."""
    from glossary_extractor import GlossaryExtractor

    extractor = GlossaryExtractor(str(output_dir), use_llm=use_llm)
    extractor.extract()
    return extractor.save_results()


def run_pipeline(
    pdf_path: Path,
    output_dir: Path = None,
    language: str = "ch",
    resume: bool = False
):
    """
    Run the full pdf2skills pipeline.

    Args:
        pdf_path: Path to input PDF file
        output_dir: Output directory (default: <pdf_name>_output)
        language: PDF language for OCR ("ch" or "en")
        resume: Whether to resume from existing progress
    """
    start_time = datetime.now()

    # Setup paths
    pdf_path = Path(pdf_path).resolve()
    if output_dir is None:
        output_dir = pdf_path.parent / f"{pdf_path.stem}_output"
    output_dir = Path(output_dir).resolve()

    print_header("pdf2skills - Full Pipeline")
    print(f"Input PDF:   {pdf_path}")
    print(f"Output Dir:  {output_dir}")
    print(f"Language:    {language}")
    print(f"Resume Mode: {resume}")
    print(f"Started:     {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    total_steps = 8
    results = {}

    # =========================================================================
    # Stage 1: PDF → Markdown (MinerU)
    # =========================================================================
    print_step(1, total_steps, "PDF to Markdown (MinerU API)")

    if resume and check_stage_complete(output_dir, "mineru"):
        print("  [SKIP] Already completed - full.md exists")
        results["mineru"] = "skipped"
    else:
        run_mineru(pdf_path, output_dir, language)
        results["mineru"] = "complete"

    markdown_path = output_dir / "full.md"
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown not found: {markdown_path}")

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
    # Stage 7: Skills → Router (Router Generator)
    # =========================================================================
    print_step(7, total_steps, "Router Generation")

    router_file = skus_dir / "router.json"

    if resume and check_stage_complete(output_dir, "router"):
        print("  [SKIP] Already completed - router.json exists")
        results["router"] = "skipped"
    else:
        run_router_generation(output_dir)
        results["router"] = "complete"

    # =========================================================================
    # Stage 8: SKUs → Glossary (Glossary Extractor)
    # =========================================================================
    print_step(8, total_steps, "Glossary Extraction")

    glossary_file = skus_dir / "glossary.json"

    if resume and check_stage_complete(output_dir, "glossary"):
        print("  [SKIP] Already completed - glossary.json exists")
        results["glossary"] = "skipped"
    else:
        run_glossary_extraction(output_dir, use_llm=False)
        results["glossary"] = "complete"

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
    print(f"    ├── full.md                        (Markdown)")
    print(f"    ├── full_chunks/                   (Chunked documents)")
    print(f"    ├── full_chunks_density/           (Density analysis)")
    print(f"    │   ├── density_scores.json")
    print(f"    │   └── heatmap.html")
    print(f"    └── full_chunks_skus/              (Knowledge units)")
    print(f"        ├── skus/                      (Individual SKUs)")
    print(f"        ├── buckets.json               (Grouped SKUs)")
    print(f"        ├── router.json                (Hierarchical router)")
    print(f"        ├── glossary.json              (Domain terminology)")
    print(f"        └── generated_skills/          (Claude Skills)")
    print(f"            ├── index.md               (Skill index)")
    print(f"            └── <skill-name>/SKILL.md  (Individual skills)")

    print(f"\nGenerated outputs ready at:")
    print(f"  Skills:   {skills_dir}")
    print(f"  Router:   {skus_dir / 'router.json'}")
    print(f"  Glossary: {skus_dir / 'glossary.json'}")

    return output_dir


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="pdf2skills - Convert PDF books to Claude Code Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a new PDF
  python run_pipeline.py book.pdf

  # Process with custom output directory
  python run_pipeline.py book.pdf --output-dir ./my_output

  # Process English PDF
  python run_pipeline.py book.pdf --language en

  # Resume from previous run
  python run_pipeline.py book.pdf --resume

  # Resume using output directory only
  python run_pipeline.py --resume ./book_output
"""
    )

    parser.add_argument(
        "input",
        help="Path to PDF file, or output directory when using --resume"
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: <pdf_name>_output)"
    )
    parser.add_argument(
        "-l", "--language",
        choices=["ch", "en"],
        default="ch",
        help="PDF language for OCR (default: ch)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing progress"
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    # Handle resume mode with directory only
    if args.resume and input_path.is_dir():
        # Input is an output directory, find the original PDF
        output_dir = input_path
        pdf_candidates = list(output_dir.parent.glob(f"{output_dir.stem.replace('_output', '')}*.pdf"))
        if pdf_candidates:
            pdf_path = pdf_candidates[0]
        else:
            # Create a dummy path since we're resuming
            pdf_path = output_dir.parent / f"{output_dir.stem.replace('_output', '')}.pdf"
    else:
        pdf_path = input_path
        output_dir = Path(args.output_dir) if args.output_dir else None

    if not args.resume and not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    try:
        run_pipeline(
            pdf_path=pdf_path,
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
