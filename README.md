# pdf2skills

Convert PDF books into Skills callable in **Trae IDE** (also supports Claude Code format).

## Quick Start

### 1. Install Dependencies

```bash
pip install requests python-dotenv python-Levenshtein numpy scikit-learn spacy jieba PyPDF2

# Download spaCy English model
python -m spacy download en_core_web_sm
```

### 2. Setup MinerU Client

Copy `mineru_client.py` to the parent directory of `pdf2skills/`:

```
your_project/
├── mineru_client.py      # MinerU API client
├── pdf2skills/           # This folder
│   ├── run_pipeline.py
│   └── ...
└── test_data/            # Your PDFs here
```

Get your MinerU API key at: https://mineru.net/

### 3. Configure Environment

Create a `.env` file in the `pdf2skills` directory:

```bash
# SiliconFlow API (Required - primary LLM provider)
SILICONFLOW_API_KEY=your_siliconflow_api_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

# MinerU API (Required - PDF to Markdown conversion)
MINERU_API_KEY=your_mineru_api_key
MINERU_BASE_URL=https://mineru.net/api/v4/extract/task

# Pipeline Configuration
CHUNK_MAX_TOKENS=30000
CHUNK_MAX_ITERATIONS=3
OUTPUT_LANGUAGE=English

# Rate Limiting (adjust based on your API tier)
GLM_RATE_LIMIT_SECONDS=3.0
FUSION_RATE_LIMIT_SECONDS=2.0
BUCKET_THRESHOLD=0.5
```

### 4. Run the Pipeline

```bash
# Basic usage (generates Trae IDE skills by default)
python run_pipeline.py your_book.pdf

# With custom output directory
python run_pipeline.py your_book.pdf --output-dir ./output

# For English PDFs
python run_pipeline.py your_book.pdf --language en

# Resume interrupted processing
python run_pipeline.py your_book.pdf --resume

# Generate Claude Code format instead of Trae IDE
python run_pipeline.py your_book.pdf --claude-format
```

### 5. Output Structure

After processing (Trae IDE format - default):

```
your_book_output/
├── full.md                          # Extracted markdown
├── full_chunks/                     # Chunked documents
│   ├── chunks_index.json
│   └── chunks/
├── full_chunks_density/             # Semantic analysis
│   ├── density_scores.json
│   └── heatmap.html                 # Visual density map
└── full_chunks_skus/                # Knowledge units
    ├── skus/                        # Individual SKU files
    ├── buckets.json                 # Grouped SKUs
    ├── router.json                  # Hierarchical router
    └── glossary.json                # Domain terminology

.trae/skills/                        # Trae IDE Skills (ready to use!)
├── <skill-name>/SKILL.md            # Individual skills
└── generation_metadata.json         # Generation info
```

### 6. Use in Trae IDE

After the pipeline completes:

1. **Restart Trae IDE** to load the new skills
2. Skills will be automatically available in your project
3. Each skill has a `description` field that tells Trae when to invoke it

## Pipeline Stages

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | MinerU API | PDF → Markdown with OCR |
| 2 | Onion Peeler | Recursive semantic chunking |
| 3 | Semantic Density | NLP scoring + LLM calibration |
| 4 | SKU Extractor | Knowledge unit extraction |
| 5 | Knowledge Fusion | Tag normalization + deduplication |
| 6 | Skill Generator | SKU → Trae Skill conversion |
| 7 | Router Generator | Hierarchical skill router |
| 8 | Glossary Extractor | Domain terminology extraction |

## Skill Format

### Trae IDE Format (Default)

Each generated skill follows the Trae IDE format:

```markdown
---
name: "skill-name"
description: "Does X. Invoke when Y happens or user asks for Z."
---

# Skill Title

<Detailed instructions, usage guidelines, and examples>
```

**Key Requirements:**
- `description` must include **WHAT** the skill does AND **WHEN** to invoke it
- Keep description under 200 characters for best display
- SKILL.md should be under 500 lines

## Using Individual Modules

Each module can be run independently:

```bash
# Chunking only
python -m onion_peeler path/to/full.md

# Density analysis only
python -m semantic_density path/to/chunks_dir

# SKU extraction only
python -m sku_extractor path/to/chunks_dir -d density_scores.json

# Knowledge fusion only
python -m knowledge_fusion path/to/skus_dir

# Skill generation only (Trae format)
python -m skill_generator path/to/skus_dir

# Skill generation only (Claude format)
python -m skill_generator path/to/skus_dir --claude-format
```

## API Providers

This project uses **SiliconFlow** as the sole LLM provider:

- **GLM-4.7** (`Pro/zai-org/GLM-4.7`) - SKU extraction, skill generation
- **DeepSeek-V3** (`deepseek-ai/DeepSeek-V3`) - Knowledge fusion
- **DeepSeek-R1** (`deepseek-ai/DeepSeek-R1`) - Density calibration
- **BGE-M3** (`Pro/BAAI/bge-m3`) - Embeddings

Get your API key at: https://siliconflow.cn/

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_MAX_TOKENS` | 30000 | Maximum tokens per chunk |
| `CHUNK_MAX_ITERATIONS` | 3 | Max recursive chunking depth |
| `OUTPUT_LANGUAGE` | English | Output language for skills |
| `GLM_RATE_LIMIT_SECONDS` | 3.0 | Delay between LLM calls |
| `BUCKET_THRESHOLD` | 0.5 | Tag overlap threshold for grouping |

## Troubleshooting

**Rate limit errors (429)**
- Increase `GLM_RATE_LIMIT_SECONDS` in `.env`
- Use `--resume` to continue from where you left off

**Memory issues with large PDFs**
- Use the `pdf_splitter.py` utility to split large PDFs
- Adjust `CHUNK_MAX_TOKENS` to smaller values

**Missing spaCy model**
```bash
python -m spacy download en_core_web_sm
```

**Skills not appearing in Trae IDE**
- Make sure skills are in `.trae/skills/` directory
- Restart Trae IDE after generating new skills
- Check that each skill has proper frontmatter with `name` and `description`

## License

MIT License

## Version

2.0 - Added Trae IDE format support
