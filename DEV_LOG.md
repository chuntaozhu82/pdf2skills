# pdf2skills Development Log

## Project Overview

**Goal:** Convert unstructured industry-specific books (PDF) into Agent Skills directly callable by Claude Code.

**Strategy:** Hybrid Model Routing - combining traditional NLP with LLMs of varying sizes for cost-effective, high-precision knowledge transcoding.

**Reference Projects:**
- `skill_seekers/` - Reference for skill structure/patterns
- `knowledge_distill_and_reform/` - Reference for knowledge extraction patterns

**Spec Document:** `../spec_draft.md`

---

## Development Progress

### Session 1: 2025-01-19 - MinerU API Integration

**Status:** COMPLETED

**Accomplished:**
1. Created `mineru_client.py` - Full MinerU API client for PDF to Markdown conversion
   - Supports file upload via presigned URLs
   - Polling for extraction completion with progress display
   - Downloads and extracts result ZIP files
   - CLI interface for easy testing

2. Successfully tested with sample PDF:
   - Input: `test_data/financial_statement_analysis_test1.pdf` (30.2 MB)
   - Output: `test_data/financial_statement_analysis_test1_output/`
     - `full.md` (670 KB) - Main markdown output
     - `layout.json` (18.6 MB) - Layout structure data
     - `content_list.json` (1.3 MB) - Content structure
     - `images/` (132 images extracted)

**API Configuration:**
- API Key stored in `.env` as `MINERU_API_KEY`
- OCR enabled for better text quality
- Formula and table extraction enabled
- Language set to Chinese (`ch`)

---

### Session 2: 2025-01-20 - LLM API Verification

**Status:** COMPLETED

**Accomplished:**
1. Verified GLM-4.7 API (BigModel)
   - Endpoint: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
   - Model: `glm-4.7`
   - Status: Working

2. Verified SiliconFlow API
   - Endpoint: `https://api.siliconflow.cn/v1`
   - Listed 127 available models
   - DeepSeek models available (16 total):
     - `deepseek-ai/DeepSeek-V3.2` (tested, working)
     - `deepseek-ai/DeepSeek-R1` (reasoning model)
     - `deepseek-ai/DeepSeek-V3`
     - `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (lightweight)
     - And more...

**API Usage Pattern (OpenAI-compatible):**
```python
# GLM-4
requests.post(f'{GLM_BASE_URL}/chat/completions',
    headers={'Authorization': f'Bearer {GLM_API_KEY}'},
    json={'model': 'glm-4.7', 'messages': [...], 'max_tokens': 128000})

# SiliconFlow (DeepSeek)
requests.post(f'{SILICONFLOW_BASE_URL}/chat/completions',
    headers={'Authorization': f'Bearer {SILICONFLOW_API_KEY}'},
    json={'model': 'deepseek-ai/DeepSeek-V3.2', 'messages': [...], 'max_tokens': 128000})
```

---

### Session 2 (continued): Onion Peeler - Recursive Chunking Agent

**Status:** COMPLETED

**Accomplished:**
1. Created `pdf2skills/onion_peeler.py` - Two-phase recursive chunking agent
   - **Phase 1 (chapter_split):** LLM analyzes header tree, decides split points
   - **Phase 2+ (recursive_peel):** LLM outputs K-nearest-neighbor anchor tokens for splits
   - Uses Levenshtein distance for fuzzy anchor matching
   - Builds tree structure with parent path inheritance

2. Added chunking configuration to `.env`:
   ```
   CHUNK_MAX_TOKENS=8000
   CHUNK_MAX_ITERATIONS=5
   CHUNK_ANCHOR_LENGTH=30
   ```

3. Successfully tested with `full.md`:
   - Phase 1: Split 670KB document into 11 chapter-level chunks
   - Phase 2: Recursively split large chunks using anchor tokens
   - Example: 28,430-token chunk → 9 smaller chunks (all under 8000 tokens)

**Key Design Decisions:**
- **Wedge concept:** LLM outputs anchor tokens (30 chars) instead of full chunks
- **Fuzzy matching:** Levenshtein distance handles OCR errors in anchors
- **Two-pass strategy:** First split by headers only (cheap), then by content (LLM reads full chunk)

**Usage:**
```python
from pdf2skills.onion_peeler import OnionPeeler
peeler = OnionPeeler('path/to/full.md')
chunks, tree = peeler.peel()
peeler.save_results('output_dir')
```

---

### Session 2 (continued): Module 2 - Semantic Density Analyzer

**Status:** COMPLETED

**Accomplished:**
1. Created `pdf2skills/semantic_density.py` - Hybrid semantic density scoring
   - **S_logic:** Logic density (connectives, reasoning patterns)
   - **S_entity:** Entity density (NER, technical terms, numbers, LaTeX)
   - **S_struct:** Structural density (lists, tables, code blocks)

2. Language-aware NLP:
   - English: Spacy (`en_core_web_sm`)
   - Chinese: Jieba + regex patterns

3. LLM Calibration with DeepSeek R1:
   - Samples 15 chunks stratified by NLP scores
   - LLM scores "gold content" (0-100 scale)
   - Linear regression to calibrate weights

4. Heatmap Output:
   - `density_scores.json` - Full scoring data
   - `heatmap.html` - Interactive bar chart visualization

5. Heatmap Visualization Improvements:
   - **Gradient colors:** Blue → Yellow → Red based on relative min/max scores
   - **Bar chart layout:** Chunks displayed in original book order (left=beginning, right=end)
   - **Mean line:** Dashed reference line showing average density
   - Shows how knowledge density changes throughout the book

6. Traceability Fields (added for knowledge unit tracking):
   - **book_index:** Sequential position in original document (0, 1, 2, ...)
   - **start_line / end_line:** Line numbers in source markdown
   - Ensures all chunks and derived knowledge units are traceable to source

**Test Results (44 chunks):**
```
Calibrated Weights:
  w_logic:  0.7776
  w_entity: 0.2224
  w_struct: 0.0000

Statistics:
  Mean: 23.53, Std: 3.17, Range: 13.35 - 31.63

Top 5 High-Value Chunks:
  1. chunk_0043: 31.6 - 权责发生制和收付实现制
  2. chunk_0017: 28.1 - 持有待售资产和持有待售负债
  3. chunk_0011: 27.3 - 获得上市公司财报
  4. chunk_0041: 26.7 - 第三章
  5. chunk_0046: 26.6 - 公允价值变动收益、投资收益和汇兑收益
```

**Usage:**
```python
from pdf2skills.semantic_density import SemanticDensityAnalyzer
analyzer = SemanticDensityAnalyzer('path/to/chunks_dir')
analyzer.save_results('output_dir')
```

---

### Session 3: 2025-01-21 - Module 3: SKU Extractor

**Status:** COMPLETED

**Accomplished:**
1. Renamed UKU to SKU (Standardized Knowledge Unit) throughout the project
   - Updated `spec_draft.md`
   - Updated `DEV_LOG.md`

2. Created `pdf2skills/sku_extractor.py` - Knowledge extraction module
   - **GLM4Client:** API client with fallback support (BigModel → SiliconFlow)
   - **Rate Limiting:** Configurable delay between API calls (default: 3s) to avoid throttling
   - **SKU Data Structure:** Full Core + Flex schema implementation
   - **MECE Extraction:** LLM extracts knowledge units following MECE principle

3. SKU Schema (Core + Flex):
   ```python
   SKU = {
       # Core Area (Invariant)
       "metadata": {"uuid", "name", "source_ref"},
       "context": {"applicable_objects", "prerequisites", "constraints"},
       "trigger": {"condition_logic"},

       # Logic Area (The "How")
       "core_logic": {"logic_type", "execution_body", "variables"},
       "output": {"output_type", "result_template"},

       # Flex Area (LLM-defined)
       "custom_attributes": {...},
       "schema_explanation": "..."
   }
   ```

4. Key Features:
   - **Density-aware extraction:** Uses density scores to estimate target SKU count per chunk
   - **Rate limiting:** `GLM_RATE_LIMIT_SECONDS` env var (default 3.0s)
   - **Fallback API:** SiliconFlow (`Pro/zai-org/GLM-4.7`) as backup
   - **Individual SKU files:** Each SKU saved as separate JSON for easy viewing/editing

5. Prompt Engineering:
   - **Location:** `pdf2skills/sku_extractor.py`, line ~227
   - **Key emphasis:** `execution_body` must be COMPREHENSIVE, preserving all details
   - Includes good/bad examples for execution_body quality

**Configuration (`.env`):**
```
GLM_RATE_LIMIT_SECONDS=3.0  # Seconds between API calls
```

**Output Structure:**
```
full_chunks_skus/
├── skus_index.json      # Index of all SKUs
└── skus/
    ├── {uuid1}.json     # Individual SKU files
    ├── {uuid2}.json
    └── ...
```

**Usage:**
```python
from pdf2skills.sku_extractor import SKUExtractor
extractor = SKUExtractor('path/to/chunks_dir', density_file='path/to/density_scores.json')
extractor.extract_all()
extractor.save_results('output_dir')
```

**CLI:**
```bash
python -m pdf2skills.sku_extractor chunks_dir -d density_scores.json -o output_dir
```

---

### Session 3 (continued): Module 4 - Knowledge Fusion (Bucketing)

**Status:** IN PROGRESS

**Accomplished:**
1. Created `pdf2skills/knowledge_fusion.py` - Tag normalization and SKU bucketing

2. **TagNormalizer** - Unifies terminology across all SKUs
   - Collects all unique `applicable_objects` and `domain_tags`
   - LLM normalizes objects (STRICT - only merge 100% identical concepts)
   - LLM normalizes tags (FLEXIBLE - merge synonyms, language variants)
   - Applies mappings back to all SKU files
   - Saves `normalization_mappings.json` for reference
   - **Prompts location:** `pdf2skills/knowledge_fusion.py`, lines ~95 and ~130

3. **SKUBucketer** - Groups related SKUs for efficient comparison
   - Uses normalized `applicable_objects` and `domain_tags`
   - Configurable threshold (`BUCKET_THRESHOLD` in `.env`, default 0.5)
   - Groups if >= threshold% overlap in objects OR tags
   - Uses Union-Find for transitive grouping (A~B, B~C => A,B,C together)
   - Handles multiple SKUs per bucket
   - Saves `buckets.json` with bucket assignments

4. **DeepSeekClient** - API client for DeepSeek V3.2 via SiliconFlow
   - Rate limiting support (`FUSION_RATE_LIMIT_SECONDS`)

**Configuration (`.env`):**
```
BUCKET_THRESHOLD=0.5  # 0-1, overlap required for grouping
FUSION_RATE_LIMIT_SECONDS=2.0  # Rate limiting for fusion API calls
```

**Output Structure:**
```
full_chunks_skus/
├── skus_index.json
├── skus/
├── normalization_mappings.json  # TagNormalizer output
└── buckets.json                 # SKUBucketer output
```

**Usage:**
```python
from pdf2skills.knowledge_fusion import TagNormalizer, SKUBucketer, run_fusion_pipeline

# Full pipeline
run_fusion_pipeline('path/to/skus_dir')

# Or separately
normalizer = TagNormalizer('path/to/skus_dir')
normalizer.normalize()

bucketer = SKUBucketer('path/to/skus_dir', threshold=0.5)
bucketer.bucket()
```

**CLI:**
```bash
# Full pipeline
python -m pdf2skills.knowledge_fusion skus_dir

# Normalize only
python -m pdf2skills.knowledge_fusion skus_dir --normalize-only

# Bucket only
python -m pdf2skills.knowledge_fusion skus_dir --bucket-only -t 0.5
```

**Design Decisions:**
- **Separate object vs tag normalization:** Objects need precision (strict), tags can be flexible
- **Threshold-based grouping:** More intuitive than similarity scores
- **Union-Find algorithm:** Efficiently handles transitive relationships
- **Smallest set denominator:** If A has 2 objects, B has 5, and they share 2, that's 100% overlap for A

---

### Session 3 (continued): Module 4.2 - Multi-Dimensional Similarity

**Status:** COMPLETED

**Accomplished:**
1. Added `EmbeddingClient` - BGE-M3 embeddings via SiliconFlow
   - Model: `Pro/BAAI/bge-m3`
   - Batch embedding support
   - Rate limiting

2. Added `SimilarityCalculator` - Multi-dimensional similarity within buckets
   - **S_anchor:** Jaccard(applicable_objects) + cosine(trigger embeddings)
   - **S_logic:** Cosine similarity of execution_body embeddings
   - **S_outcome:** Cosine similarity of output/result_template embeddings

3. Relationship Classification (from spec):
   | State | Condition | Action |
   |-------|-----------|--------|
   | **Duplicate** | High anchor + High logic + High outcome | Merge descriptions |
   | **Conflict** | High anchor + Low outcome | Generate branching logic |
   | **Independent** | Low anchor | Keep original |

4. Thresholds:
   - HIGH_THRESHOLD = 0.7
   - LOW_THRESHOLD = 0.3

**Output:**
```
full_chunks_skus/
├── ...
└── similarities.json   # SimilarityCalculator output
    ├── metadata (counts, thresholds)
    ├── duplicates (pairs to merge)
    ├── conflicts (pairs needing resolution)
    └── all_similarities (full list)
```

**Usage:**
```python
from pdf2skills.knowledge_fusion import SimilarityCalculator

calculator = SimilarityCalculator('path/to/skus_dir')
calculator.calculate()
```

**CLI:**
```bash
# Similarity only (requires buckets.json)
python -m pdf2skills.knowledge_fusion skus_dir --similarity-only

# Full pipeline (normalize + bucket + similarity)
python -m pdf2skills.knowledge_fusion skus_dir
```

---

### Session 3 (continued): Module 4.3 - State Matrix & Resolution

**Status:** COMPLETED (Code Ready)

**Accomplished:**
1. Added `StateMatrix` - Maps similarity results to resolution actions
   - Categorizes all similarity pairs into states
   - Creates `ResolutionTask` objects for duplicates and conflicts
   - Independent pairs (low anchor similarity) are kept as-is

2. State Classification (from spec):
   | State Code | Name | Condition | Action |
   |------------|------|-----------|--------|
   | 1 | Duplicate | High anchor + High logic + High outcome | Merge descriptions |
   | -1 | Conflict | High anchor + Low outcome | Generate branching logic |
   | 0 | Independent | Low anchor | Keep original |

3. Added `ResolutionTask` dataclass:
   ```python
   @dataclass
   class ResolutionTask:
       task_id: str
       state: int           # 1=duplicate, -1=conflict, 0=independent
       uuid1: str
       uuid2: str
       name1: str
       name2: str
       similarity: dict     # S_anchor, S_logic, S_outcome scores
       action: str          # "merge" | "branch" | "keep"
       resolved: bool
       result: Optional[dict]
   ```

4. Added `SKUResolver` - Executes merge/branch actions using LLM
   - **Merge (duplicates):** Combines two SKUs preserving all unique details
   - **Branch (conflicts):** Creates conditional IF-ELSE logic with clear applicability rules
   - Original SKUs marked as deprecated (adds `deprecated_by` field)
   - New resolved SKUs saved to `resolved_skus/` directory

5. LLM Prompts:
   - **MERGE_PROMPT:** Located at line ~1325 in `knowledge_fusion.py`
     - Combines execution_body, output, custom_attributes
     - Preserves all unique information from both SKUs
   - **BRANCH_PROMPT:** Located at line ~1374 in `knowledge_fusion.py`
     - Creates clear IF-ELSE branching logic
     - Identifies differentiating conditions between conflicting SKUs

**Output Structure:**
```
full_chunks_skus/
├── skus/                    # Original SKUs (may have deprecated_by field)
├── similarities.json        # From SimilarityCalculator
├── state_matrix.json        # StateMatrix output
│   ├── duplicates[]         # Tasks with action="merge"
│   ├── conflicts[]          # Tasks with action="branch"
│   └── summary              # Counts and statistics
├── resolved_skus/           # SKUResolver output
│   ├── {new_uuid}.json      # Merged/branched SKUs
│   └── ...
└── resolution_summary.json  # SKUResolver summary
    ├── total_resolved
    ├── merge_count
    ├── branch_count
    ├── failed_count
    └── tasks[]              # Detailed task results
```

**Usage:**
```python
from pdf2skills.knowledge_fusion import StateMatrix, SKUResolver

# Build state matrix from similarities
matrix = StateMatrix('path/to/skus_dir')
matrix.build()  # Reads similarities.json, outputs state_matrix.json

# Execute resolution
resolver = SKUResolver('path/to/skus_dir')
resolver.resolve_all()  # Reads state_matrix.json, outputs resolved_skus/
```

**CLI:**
```bash
# State matrix only
python -m pdf2skills.knowledge_fusion skus_dir --matrix-only

# Resolve only (requires state_matrix.json)
python -m pdf2skills.knowledge_fusion skus_dir --resolve-only

# Full pipeline (normalize + bucket + similarity + matrix + resolve)
python -m pdf2skills.knowledge_fusion skus_dir --full
```

**Design Decisions:**
- **Non-destructive resolution:** Original SKUs kept, just marked deprecated
- **New UUIDs for resolved SKUs:** Clean lineage tracking via `source_refs`
- **Separate state matrix:** Allows manual review before resolution
- **Incremental resolution:** Can re-run resolver after manual edits to state_matrix.json

---

### Session 4: 2025-01-21 - Module 5: Skill Generator

**Status:** COMPLETED (Code Ready)

**Accomplished:**
1. Created `pdf2skills/skill_generator.py` - Converts SKUs to Claude Code Skills

2. **SkillGenerator** class with:
   - N:M mapping (M ≤ N) - LLM decides how to merge/split SKUs into skills
   - Bucket-aware processing - generates skills per bucket
   - Large bucket handling - splits into chunks of MAX_SKUS_PER_LLM_CALL (15)
   - Post-processing - packages LLM output into proper folder structure

3. **Two-Level Output Structure:**
   ```
   generated_skills/
   ├── index.md                    # Top-level router/instruction
   ├── skill-name-1/
   │   ├── SKILL.md               # Core workflow (< 500 lines)
   │   └── references/
   │       └── details.md         # Detailed examples, formulas
   ├── skill-name-2/
   │   └── SKILL.md
   └── generation_metadata.json   # Tracking which SKUs → which skills
   ```

4. **LLM Prompts:**
   - **SKILL_GENERATION_PROMPT** (line ~95): Converts SKUs to skills
     - Instructs LLM on merge/split decisions
     - Enforces < 500 line limit for SKILL.md
     - Requires kebab-case naming, clear descriptions
   - **INDEX_GENERATION_PROMPT** (line ~165): Creates top-level router
     - Summarizes all skills
     - Creates navigation table
     - Groups by category

5. **Follows Anthropic's Official Skill Guide:**
   - YAML frontmatter with `name` and `description`
   - Description includes WHAT and WHEN to trigger
   - Core procedures in SKILL.md, details in references/
   - Imperative writing style

**Usage:**
```python
from pdf2skills.skill_generator import SkillGenerator, run_skill_generation

# Full pipeline
run_skill_generation('path/to/skus_dir', 'path/to/output')

# Or step by step
generator = SkillGenerator('path/to/skus_dir')
generator.generate_all()
generator.package_skills()
```

**CLI:**
```bash
# Full generation
python -m pdf2skills.skill_generator skus_dir -o generated_skills

# Update index.md only (after manually adding/removing skills)
python -m pdf2skills.skill_generator generated_skills --update-index
```

**Design Decisions:**
- **N:M mapping:** LLM autonomously decides merge/split based on SKU similarity
- **Chunked processing:** Large buckets split to avoid context overflow
- **Metadata tracking:** `generation_metadata.json` records SKU → Skill lineage
- **Fallback index:** Simple list if LLM fails to generate fancy index
- **Incremental index:** index.md is updated (not rewritten) on each run, preserving manual edits

---

## Module Progress

### Module 1: Document Parsing & Chunking - COMPLETED
- [x] MinerU PDF → Markdown conversion
- [x] Onion Peeler recursive chunking
- [x] Parent path inheritance

### Module 2: Semantic Density Scoring - COMPLETED
- [x] NLP feature extraction (logic, entity, struct)
- [x] LLM calibration with DeepSeek R1
- [x] Heatmap visualization (JSON + HTML)

### Module 3: SKU Schema - COMPLETED
- [x] Design SKU data structure (Core + Flex)
- [x] GLM-4.7 client with rate limiting and fallback
- [x] Extract knowledge units from chunks (MECE principle)
- [x] Save individual SKU JSON files

### Module 4: Knowledge Fusion - COMPLETED
- [x] Tag Normalization (TagNormalizer)
- [x] Bucketing by domain/tags (SKUBucketer)
- [x] Multi-dimensional similarity (SimilarityCalculator)
- [x] State Matrix (StateMatrix) - categorizes pairs, prepares resolution tasks
- [x] Duplicate/conflict resolution (SKUResolver) - merge + branching logic

**Known Issues to Fix:**
- [ ] **Tag Coherence Problem:** SKUs extracted in separate LLM calls may use inconsistent terminology for same concepts (e.g., "财务分析" vs "financial analysis" vs "Financial Analysis").
  - **Solution implemented:** TagNormalizer class - post-extraction LLM pass to normalize tags
  - **TODO after testing:** Evaluate if normalization is sufficient or if pre-defined taxonomy needed

- [x] **Large Bucket Problem:** First bucket often contains 80%+ of all SKUs because books are already focused on a specific domain. Bucketing by tag overlap isn't granular enough.
  - **Solution implemented:** `BucketRefiner` class - recursively divides large buckets until each is under 32k tokens
  - Uses similarity scores to guide splits (similar SKUs stay together)
  - CLI: `python -m pdf2skills.knowledge_fusion skus_dir --refine-buckets --max-tokens 32000`

- [ ] **Inconsistent Flex Schema:** SKUs may have inconsistent `custom_attributes` structures since each LLM call independently decides the flex fields.
  - **TODO:** Post-extraction pass to unify flex schema, or pre-define taxonomy of allowed custom attributes per domain

### Module 5: Claude Skills Generation - COMPLETED
- [x] SkillGenerator class with N:M mapping
- [x] SKU-to-Skill conversion prompt (GLM-4.7)
- [x] Post-processing into folder structure
- [x] Top-level index.md generation
- [x] Metadata tracking (generation_metadata.json)

---

## Architecture Notes

### Module Pipeline (from spec):
```
Module 1: PDF → Markdown → AST → Chunks (with metadata)
Module 2: Chunks → Semantic Density Scoring → Knowledge Heatmap
Module 3: Chunks → SKU (Standardized Knowledge Unit) Schema
Module 4: SKUs → Knowledge Fusion (dedup/conflict resolution)
Module 5: Fused SKUs → Claude Skills Directory
```

### LLM Usage Strategy (SiliconFlow - Sole Provider):
- **SKU Extraction / Skill Generation:** GLM-4.7 (`Pro/zai-org/GLM-4.7`)
- **Knowledge Fusion:** DeepSeek-V3 (`deepseek-ai/DeepSeek-V3`)
- **Density Calibration:** DeepSeek-R1 (`deepseek-ai/DeepSeek-R1`)
- **Embeddings:** BGE-M3 (`Pro/BAAI/bge-m3`)
- **PDF Parsing:** MinerU API

### Output Structure Target:
```
~/.claude/skills/generated_book_skills/
├── manifest.json
├── skill-domain-A/
│   ├── SKILL.md
│   ├── solver.py
│   └── tests/
└── skill-domain-B/
    └── ...
```

---

## File Structure

```
cc_projects/
├── .env                          # API keys (parent directory)
├── spec_draft.md                 # Full project specification
├── mineru_client.py              # MinerU API client (Module 1.1)
├── pdf2skills/                   # Main project directory
│   ├── .env                     # API keys + pipeline config
│   ├── README.md                # Quick start guide
│   ├── DEV_LOG.md               # This file
│   ├── run_pipeline.py          # End-to-end pipeline runner
│   ├── onion_peeler.py          # Recursive chunking (Module 1)
│   ├── semantic_density.py      # Density scoring (Module 2)
│   ├── sku_extractor.py         # SKU extraction (Module 3)
│   ├── knowledge_fusion.py      # Tag normalization & bucketing (Module 4)
│   ├── skill_generator.py       # SKU to Claude Skills (Module 5)
│   └── pdf_splitter.py          # PDF splitting utility
├── test_data/
│   ├── financial_statement_analysis_test1.pdf
│   └── financial_statement_analysis_test1_output/
│       ├── full.md              # MinerU output
│       ├── full_chunks/         # Onion Peeler output
│       │   ├── tree.json
│       │   ├── chunks_index.json
│       │   └── chunks/
│       ├── full_chunks_density/ # Semantic Density output
│       │   ├── density_scores.json
│       │   └── heatmap.html
│       └── full_chunks_skus/    # SKU Extractor output
│           ├── skus_index.json
│           ├── skus/
│           ├── normalization_mappings.json  # TagNormalizer output
│           ├── buckets.json                 # SKUBucketer output
│           ├── similarities.json            # SimilarityCalculator output
│           └── generated_skills/            # Skill Generator output
│               ├── index.md                 # Top-level router
│               ├── generation_metadata.json # SKU → Skill mapping
│               └── skill-name/
│                   ├── SKILL.md
│                   └── references/
└── skills/                      # Official Claude Skills (reference)
```

## Claude Skills Format (from official reference)

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter: name, description
│   └── Markdown: instructions, workflows
├── scripts/      (optional) - Executable code
├── references/   (optional) - Documentation
└── assets/       (optional) - Templates, images
```

---

### Session 5: 2025-01-22 - Version 1.0 Release

**Status:** RELEASED

**Accomplished:**
1. Removed partial test/batch processing files:
   - `batch_process.py`
   - `batch_full_pipeline.py`
   - `batch_sku_extract.py`
   - `batch_fusion_test.py`
   - `process_large_pdf.py`
   - `run_skill_gen_with_progress.py`

2. Created `run_pipeline.py` - End-to-end full pipeline runner
   - 6-stage pipeline: MinerU → Onion Peeler → Semantic Density → SKU Extractor → Knowledge Fusion → Skill Generator
   - Resume support with `--resume` flag
   - Progress tracking and stage completion detection
   - CLI with `--language`, `--output-dir` options

3. Created `README.md` - Quick start guide
   - Installation instructions
   - Environment configuration
   - Basic usage examples
   - Module-by-module CLI reference
   - Troubleshooting section

4. Consolidated LLM provider to SiliconFlow only
   - Removed/commented out BigModel (GLM-4.7) direct API calls
   - All LLM calls now go through SiliconFlow:
     - GLM-4.7: `Pro/zai-org/GLM-4.7` (SKU extraction, skill generation)
     - DeepSeek-V3: `deepseek-ai/DeepSeek-V3` (knowledge fusion)
     - DeepSeek-R1: `deepseek-ai/DeepSeek-R1` (density calibration)
     - BGE-M3: `Pro/BAAI/bge-m3` (embeddings)

5. Updated documentation to reflect SiliconFlow as sole provider

**Usage:**
```bash
# Full pipeline
python run_pipeline.py book.pdf

# With options
python run_pipeline.py book.pdf --language en --output-dir ./output

# Resume interrupted run
python run_pipeline.py book.pdf --resume
```

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | 2025-01-22 | Initial release - Full pipeline with SiliconFlow |

---

## Session Notes

### How to Resume Development
1. Read this DEV_LOG.md for context
2. Reference `spec_draft.md` for detailed requirements
3. Run pipeline: `python run_pipeline.py test_data/your_book.pdf`
