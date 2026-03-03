#!/usr/bin/env python3
"""
Any2Skill - Full Pipeline Runner

End-to-end pipeline for converting various input sources to Trae IDE Skills.

Supported input formats:
- PDF files (.pdf)
- Text files (.txt)
- Markdown files (.md)
- Web URLs (http:// or https://)
- URL list files (.txt with URLs)

Pipeline stages:
1. Input → Markdown (MinerU API / Text Processor / Web Scraper)
2. Markdown → Chunks (Onion Peeler)
3. Chunks → Density Scores (Semantic Density Analyzer)
4. Chunks → SKUs (SKU Extractor)
5. SKUs → Fused SKUs (Knowledge Fusion)
6. Fused SKUs → Trae Skills (Skill Generator)
7. All Outputs → Router (Router Generator)
8. SKUs → Glossary (Glossary Extractor)

Usage:
    python run_pipeline.py <input> [--output-dir <dir>] [options]
    
    # PDF file
    python run_pipeline.py book.pdf
    
    # Text file
    python run_pipeline.py notes.txt
    
    # Markdown file
    python run_pipeline.py document.md
    
    # Web URL
    python run_pipeline.py https://example.com/article
    
    # URL list file
    python run_pipeline.py urls.txt
    
    # Resume from previous run
    python run_pipeline.py --resume ./book_output
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

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


def detect_input_type(input_path: str) -> Tuple[str, str]:
    """
    Detect the type of input.
    
    Returns:
        Tuple of (input_type, description)
        input_type: 'pdf', 'txt', 'md', 'url', 'url_list', 'unknown'
    """
    if input_path.startswith('http://') or input_path.startswith('https://'):
        return 'url', 'Web URL'
    
    path = Path(input_path)
    
    if not path.exists():
        return 'unknown', 'File not found'
    
    suffix = path.suffix.lower()
    
    if suffix == '.pdf':
        return 'pdf', 'PDF file'
    elif suffix == '.md':
        return 'md', 'Markdown file'
    elif suffix == '.txt':
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            first_lines = [f.readline() for _ in range(10)]
        
        url_count = sum(1 for line in first_lines if line.strip().startswith('http'))
        if url_count >= 2:
            return 'url_list', 'URL list file'
        
        return 'txt', 'Text file'
    
    return 'unknown', f'Unsupported format: {suffix}'


def run_input_to_markdown(input_path: str, output_dir: Path, input_type: str, language: str = "ch") -> Path:
    """Stage 1: Convert input to Markdown based on type."""
    markdown_path = output_dir / "full.md"
    
    if input_type == 'pdf':
        from mineru_client import MineruClient
        client = MineruClient(language=language)
        return client.convert_pdf(Path(input_path), output_dir)
    
    elif input_type in ('txt', 'md'):
        from text_processor import TextProcessor
        processor = TextProcessor(input_path, str(output_dir))
        return processor.process()
    
    elif input_type == 'url':
        from web_scraper import WebScraper
        scraper = WebScraper(str(output_dir))
        result = scraper.scrape_url(input_path)
        if result is None:
            raise RuntimeError(f"Failed to scrape URL: {input_path}")
        return result
    
    elif input_type == 'url_list':
        from web_scraper import WebScraper
        scraper = WebScraper(str(output_dir))
        result = scraper.scrape_url_list_file(input_path, combine=True)
        if result is None:
            raise RuntimeError(f"Failed to scrape URLs from: {input_path}")
        return result
    
    else:
        raise ValueError(f"Unsupported input type: {input_type}")


def check_stage_complete(output_dir: Path, stage: str, trae_format: bool = True) -> bool:
    """Check if a pipeline stage has already completed."""
    if trae_format and stage == "skills":
        marker = output_dir.parent / ".trae" / "skills" / "generation_metadata.json"
    else:
        markers = {
            "input": output_dir / "full.md",
            "chunks": output_dir / "full_chunks" / "chunks_index.json",
            "density": output_dir / "full_chunks_density" / "density_scores.json",
            "skus": output_dir / "full_chunks_skus" / "skus_index.json",
            "fusion": output_dir / "full_chunks_skus" / "buckets.json",
            "skills": output_dir / "full_chunks_skus" / "generated_skills" / "generation_metadata.json",
            "router": output_dir / "full_chunks_skus" / "router.json",
            "glossary": output_dir / "full_chunks_skus" / "glossary.json",
        }
        marker = markers.get(stage, Path(""))
    return marker.exists()


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

    print("\n  5.1 Tag Normalization...")
    normalizer = TagNormalizer(str(skus_dir))
    normalizer.normalize()
    results["normalization"] = "complete"

    print("\n  5.2 SKU Bucketing...")
    bucketer = SKUBucketer(str(skus_dir))
    bucketer.bucket()
    results["bucketing"] = "complete"

    print("\n  5.3 Similarity Calculation...")
    calculator = SimilarityCalculator(str(skus_dir))
    calculator.calculate()
    results["similarity"] = "complete"

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


def run_skill_generation(skus_dir: Path, output_dir: Path = None, trae_format: bool = True) -> Path:
    """Stage 6: Generate Trae IDE Skills from SKUs.
    
    Args:
        skus_dir: Path to SKUs directory
        output_dir: Optional output directory
        trae_format: If True, output in Trae IDE format (.trae/skills/)
    """
    from skill_generator import SkillGenerator

    generator = SkillGenerator(str(skus_dir), str(output_dir) if output_dir else None, trae_format=trae_format)
    generator.generate_all()
    generator.package_skills()

    return generator.output_dir


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


def get_output_name(input_path: str, input_type: str) -> str:
    """Generate output directory name from input."""
    if input_type in ('url', 'url_list'):
        if input_type == 'url':
            from urllib.parse import urlparse
            parsed = urlparse(input_path)
            name = parsed.netloc.replace('.', '_')
            if parsed.path and parsed.path != '/':
                path_name = parsed.path.strip('/').replace('/', '_')
                name = f"{name}_{path_name[:30]}"
            return name[:50]
        else:
            return Path(input_path).stem
    else:
        return Path(input_path).stem


def run_pipeline(
    input_path: str,
    output_dir: Path = None,
    input_type: str = None,
    language: str = "ch",
    resume: bool = False,
    trae_format: bool = True
):
    """
    Run the full Any2Skill pipeline.

    Args:
        input_path: Path to input file or URL
        output_dir: Output directory (default: <input_name>_output)
        input_type: Override input type detection
        language: PDF language for OCR ("ch" or "en")
        resume: Whether to resume from existing progress
        trae_format: If True, generate Trae IDE compatible skills
    """
    start_time = datetime.now()

    if input_type is None:
        input_type, input_desc = detect_input_type(input_path)
    else:
        input_desc = input_type

    if input_type == 'unknown':
        print(f"Error: {input_desc}")
        sys.exit(1)

    output_name = get_output_name(input_path, input_type)
    if output_dir is None:
        output_dir = Path(input_path).parent / f"{output_name}_output" if input_type not in ('url', 'url_list') else Path(f"./{output_name}_output")
    output_dir = Path(output_dir).resolve()

    print_header("Any2Skill - Full Pipeline")
    print(f"Input:       {input_path}")
    print(f"Input Type:  {input_desc}")
    print(f"Output Dir:  {output_dir}")
    print(f"Language:    {language}")
    print(f"Resume Mode: {resume}")
    print(f"Skill Format: {'Trae IDE' if trae_format else 'Claude Code'}")
    print(f"Started:     {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    total_steps = 8
    results = {}

    # =========================================================================
    # Stage 1: Input → Markdown
    # =========================================================================
    print_step(1, total_steps, f"Input to Markdown ({input_desc})")

    if resume and check_stage_complete(output_dir, "input"):
        print("  [SKIP] Already completed - full.md exists")
        results["input"] = "skipped"
    else:
        run_input_to_markdown(input_path, output_dir, input_type, language)
        results["input"] = "complete"

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
    # Stage 6: SKUs → Trae Skills (Skill Generator)
    # =========================================================================
    print_step(6, total_steps, "Skill Generation")

    if resume and check_stage_complete(output_dir, "skills", trae_format=trae_format):
        print("  [SKIP] Already completed - skills exist")
        results["skills"] = "skipped"
    else:
        skills_output = run_skill_generation(skus_dir, trae_format=trae_format)
        results["skills"] = "complete"
        results["skills_dir"] = str(skills_output)

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
    if trae_format:
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
        print(f"        └── glossary.json              (Domain terminology)")
        print(f"  ")
        print(f"  .trae/skills/                        (Trae IDE Skills)")
        print(f"      ├── <skill-name>/SKILL.md        (Individual skills)")
        print(f"      └── generation_metadata.json     (Generation info)")
    else:
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

    skills_dir = results.get("skills_dir", str(skus_dir / "generated_skills"))
    print(f"\nGenerated outputs ready at:")
    print(f"  Skills:   {skills_dir}")
    print(f"  Router:   {skus_dir / 'router.json'}")
    print(f"  Glossary: {skus_dir / 'glossary.json'}")
    
    if trae_format:
        print(f"\n✅ Skills are ready for Trae IDE!")
        print(f"   Restart Trae IDE to load the new skills.")

    return output_dir


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Any2Skill - Convert any input to Trae IDE Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a PDF file
  python run_pipeline.py book.pdf
  
  # Process a text file
  python run_pipeline.py notes.txt
  
  # Process a markdown file
  python run_pipeline.py document.md
  
  # Scrape a web page
  python run_pipeline.py https://example.com/article
  
  # Scrape multiple URLs from a file
  python run_pipeline.py urls.txt
  
  # Process with custom output directory
  python run_pipeline.py book.pdf --output-dir ./my_output
  
  # Process English PDF
  python run_pipeline.py book.pdf --language en
  
  # Resume from previous run
  python run_pipeline.py book.pdf --resume
  
  # Resume using output directory only
  python run_pipeline.py --resume ./book_output
  
  # Generate Claude Code format instead of Trae IDE
  python run_pipeline.py book.pdf --claude-format
"""
    )

    parser.add_argument(
        "input",
        nargs='?',
        help="Input: PDF file, TXT file, MD file, URL, or URL list file"
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: <input_name>_output)"
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
    parser.add_argument(
        "--claude-format",
        action="store_true",
        help="Generate Claude Code format skills instead of Trae IDE format"
    )
    parser.add_argument(
        "--type",
        choices=["pdf", "txt", "md", "url", "url_list"],
        help="Override input type detection"
    )

    args = parser.parse_args()

    if not args.input and not args.resume:
        parser.print_help()
        print("\nError: Input is required (unless using --resume with a directory)")
        sys.exit(1)

    input_path = args.input

    if args.resume and input_path:
        resume_path = Path(input_path)
        if resume_path.is_dir():
            output_dir = resume_path
            parent_files = list(output_dir.parent.glob(f"{output_dir.stem.replace('_output', '')}.*"))
            pdf_files = [f for f in parent_files if f.suffix.lower() == '.pdf']
            if pdf_files:
                input_path = str(pdf_files[0])
            else:
                txt_files = [f for f in parent_files if f.suffix.lower() in ('.txt', '.md')]
                if txt_files:
                    input_path = str(txt_files[0])
                else:
                    input_path = output_dir.stem.replace('_output', '')
        else:
            output_dir = Path(args.output_dir) if args.output_dir else None
    else:
        output_dir = Path(args.output_dir) if args.output_dir else None

    if not args.resume:
        input_type, input_desc = detect_input_type(input_path)
        if input_type == 'unknown':
            print(f"Error: {input_desc}")
            sys.exit(1)
        
        if input_type == 'pdf':
            if not Path(input_path).exists():
                print(f"Error: File not found: {input_path}")
                sys.exit(1)
    else:
        input_type = args.type

    try:
        run_pipeline(
            input_path=input_path,
            output_dir=output_dir,
            input_type=input_type,
            language=args.language,
            resume=args.resume,
            trae_format=not args.claude_format
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
