#!/usr/bin/env python3
"""
Semantic Density Analyzer (Module 2)

This module calculates semantic density scores for document chunks to identify
high-value "mining zones" for knowledge extraction.

Three-dimensional NLP scoring:
- S_logic: Logic density (connectives, reasoning patterns)
- S_entity: Entity density (NER, technical terms, numbers, formulas)
- S_struct: Structural density (lists, tables, code blocks)

Adaptive weighting via LLM calibration using DeepSeek R1.
"""

import os
import re
import json
import random
import requests
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
from sklearn.linear_model import LinearRegression
from pathlib import Path

# Load .env from pdf2skills directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Configuration
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL")
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")

# Detect source language from OUTPUT_LANGUAGE or content
# For now, we use a simple heuristic based on content


@dataclass
class ChunkScore:
    """Scores for a single chunk."""
    chunk_id: str
    title: str
    parent_path: list[str]
    book_index: int = 0  # Position in the original book (0-indexed)
    start_line: int = 0  # Start line in source markdown
    end_line: int = 0    # End line in source markdown
    s_logic: float = 0.0
    s_entity: float = 0.0
    s_struct: float = 0.0
    gold_score: Optional[float] = None  # LLM-assigned score (0-100)
    final_score: float = 0.0
    content_preview: str = ""
    token_count: int = 0

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "book_index": self.book_index,
            "title": self.title,
            "parent_path": self.parent_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "s_logic": round(self.s_logic, 4),
            "s_entity": round(self.s_entity, 4),
            "s_struct": round(self.s_struct, 4),
            "gold_score": self.gold_score,
            "final_score": round(self.final_score, 4),
            "content_preview": self.content_preview,
            "token_count": self.token_count
        }


class NLPAnalyzer:
    """Language-aware NLP feature extractor."""

    def __init__(self, language: str = "auto"):
        """
        Initialize NLP analyzer.

        Args:
            language: "English", "Chinese", or "auto" (detect from content)
        """
        self.language = language
        self._spacy_model = None
        self._jieba_loaded = False

    def _detect_language(self, text: str) -> str:
        """Detect if text is primarily Chinese or English."""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.replace(' ', '').replace('\n', ''))
        if total_chars == 0:
            return "English"
        chinese_ratio = chinese_chars / total_chars
        return "Chinese" if chinese_ratio > 0.3 else "English"

    def _get_language(self, text: str) -> str:
        """Get the language to use for analysis."""
        if self.language == "auto":
            return self._detect_language(text)
        return self.language

    def _load_spacy(self):
        """Lazy load spacy model for English."""
        if self._spacy_model is None:
            import spacy
            try:
                self._spacy_model = spacy.load("en_core_web_sm")
            except OSError:
                print("Downloading spacy English model...")
                spacy.cli.download("en_core_web_sm")
                self._spacy_model = spacy.load("en_core_web_sm")
        return self._spacy_model

    def _load_jieba(self):
        """Lazy load jieba for Chinese."""
        if not self._jieba_loaded:
            import jieba
            jieba.setLogLevel(jieba.logging.INFO)
            self._jieba_loaded = True
        import jieba
        return jieba

    # =========================================================================
    # S_logic: Logic Density
    # =========================================================================

    def calc_s_logic(self, text: str) -> float:
        """
        Calculate logic density score.

        Measures:
        - Frequency of logical connectives
        - Conditional/causal patterns
        - Reasoning indicators
        """
        lang = self._get_language(text)
        text_lower = text.lower()
        word_count = max(1, len(text.split()))

        if lang == "Chinese":
            # Chinese logical connectives
            connectives = [
                r'如果', r'那么', r'因此', r'所以', r'由于', r'因为',
                r'但是', r'然而', r'虽然', r'尽管', r'除非', r'否则',
                r'必须', r'应该', r'需要', r'导致', r'造成', r'引起',
                r'首先', r'其次', r'最后', r'总之', r'综上',
                r'当.*时', r'若.*则', r'只有.*才', r'不仅.*而且',
                r'一方面.*另一方面', r'根据', r'按照', r'依据'
            ]
            # Count matches
            count = sum(len(re.findall(p, text)) for p in connectives)
            # Normalize by character count (Chinese)
            char_count = max(1, len(text.replace(' ', '').replace('\n', '')))
            score = (count / char_count) * 100

        else:  # English
            connectives = [
                r'\bif\b', r'\bthen\b', r'\btherefore\b', r'\bthus\b',
                r'\bbecause\b', r'\bsince\b', r'\bhence\b', r'\bso\b',
                r'\bhowever\b', r'\bbut\b', r'\balthough\b', r'\bwhile\b',
                r'\bmust\b', r'\bshould\b', r'\brequire[sd]?\b', r'\bneed[sd]?\b',
                r'\blead[s]?\s+to\b', r'\bresult[s]?\s+in\b', r'\bcause[sd]?\b',
                r'\bfirst\b', r'\bsecond\b', r'\bfinally\b', r'\bin\s+conclusion\b',
                r'\bwhen\b', r'\bunless\b', r'\bprovided\s+that\b',
                r'\baccording\s+to\b', r'\bbased\s+on\b', r'\bgiven\s+that\b'
            ]
            count = sum(len(re.findall(p, text_lower)) for p in connectives)
            score = (count / word_count) * 100

        # Also check for dependency depth via sentence complexity
        avg_sentence_len = self._avg_sentence_length(text)
        complexity_bonus = min(avg_sentence_len / 50, 1.0) * 20  # Max 20 bonus

        return min(100, score + complexity_bonus)

    def _avg_sentence_length(self, text: str) -> float:
        """Calculate average sentence length."""
        sentences = re.split(r'[.!?。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return 0
        return sum(len(s) for s in sentences) / len(sentences)

    # =========================================================================
    # S_entity: Entity Density
    # =========================================================================

    def calc_s_entity(self, text: str) -> float:
        """
        Calculate entity density score.

        Measures:
        - Named entities (NER)
        - Technical terminology
        - Numbers, percentages, currency
        - LaTeX formulas
        """
        lang = self._get_language(text)
        char_count = max(1, len(text.replace(' ', '').replace('\n', '')))

        # Count numbers, percentages, currency
        numbers = len(re.findall(r'\d+(?:\.\d+)?%?', text))
        currency = len(re.findall(r'[$¥€£]\s*\d+|\d+\s*(?:元|美元|万|亿|千)', text))

        # Count LaTeX formulas
        latex = len(re.findall(r'\$[^$]+\$|\\\[.*?\\\]|\\\(.*?\\\)', text))

        # Count technical patterns (parenthetical definitions, abbreviations)
        tech_patterns = len(re.findall(r'\([A-Z]{2,}\)', text))  # (ABC) style abbreviations
        tech_patterns += len(re.findall(r'「[^」]+」|"[^"]+"', text))  # Quoted terms

        if lang == "Chinese":
            # Chinese NER patterns (simplified)
            # Company names, person names, financial terms
            ner_patterns = [
                r'[\u4e00-\u9fff]{2,4}(?:公司|集团|银行|基金|股份)',  # Company
                r'[\u4e00-\u9fff]{2,3}(?:率|额|值|数|量)',  # Financial metrics
                r'(?:总|净|毛)?(?:收入|利润|资产|负债|现金流)',  # Accounting terms
            ]
            ner_count = sum(len(re.findall(p, text)) for p in ner_patterns)

            # Use jieba for word segmentation and count proper nouns
            jieba = self._load_jieba()
            import jieba.posseg as pseg
            words = pseg.cut(text[:5000])  # Limit for performance
            proper_nouns = sum(1 for w, flag in words if flag in ['nr', 'ns', 'nt', 'nz'])
            ner_count += proper_nouns

        else:  # English
            # Use spacy for NER
            nlp = self._load_spacy()
            doc = nlp(text[:10000])  # Limit for performance
            ner_count = len(doc.ents)

            # Technical term patterns
            tech_terms = len(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text))  # CamelCase
            ner_count += tech_terms

        # Combine scores
        total_entities = numbers + currency + latex + tech_patterns + ner_count
        score = (total_entities / char_count) * 500  # Scale factor

        return min(100, score)

    # =========================================================================
    # S_struct: Structural Density
    # =========================================================================

    def calc_s_struct(self, text: str) -> float:
        """
        Calculate structural density score.

        Measures:
        - List items (bullet points, numbered lists)
        - Table rows
        - Code blocks
        - Headers
        """
        lines = text.split('\n')
        total_lines = max(1, len(lines))

        # Count list items
        bullet_lists = sum(1 for line in lines if re.match(r'^\s*[-*+•]\s+', line))
        numbered_lists = sum(1 for line in lines if re.match(r'^\s*\d+[.)]\s+', line))
        chinese_lists = sum(1 for line in lines if re.match(r'^\s*[（(][一二三四五六七八九十\d]+[)）]', line))

        # Count table indicators
        table_rows = sum(1 for line in lines if '|' in line and line.count('|') >= 2)

        # Count code blocks
        code_blocks = len(re.findall(r'```[\s\S]*?```', text))
        inline_code = len(re.findall(r'`[^`]+`', text))

        # Count headers
        headers = sum(1 for line in lines if re.match(r'^#{1,6}\s+', line))

        # Combine scores
        struct_elements = (
            bullet_lists + numbered_lists + chinese_lists +
            table_rows * 0.5 +  # Tables often have many rows
            code_blocks * 3 +   # Code blocks are high-value
            inline_code * 0.3 +
            headers * 2
        )

        score = (struct_elements / total_lines) * 100

        return min(100, score)


class DeepSeekR1Client:
    """Client for DeepSeek R1 reasoning model via SiliconFlow."""

    def __init__(self):
        self.model = "deepseek-ai/DeepSeek-R1"
        self.api_key = SILICONFLOW_API_KEY
        self.base_url = SILICONFLOW_BASE_URL

    def score_chunk(self, chunk_content: str, chunk_title: str, parent_path: list[str]) -> int:
        """
        Score a chunk's "gold content" value (0-100).

        Uses DeepSeek R1 reasoning model to evaluate knowledge density.
        """
        path_str = " > ".join(parent_path + [chunk_title]) if parent_path else chunk_title

        prompt = f"""You are an expert knowledge evaluator. Your task is to assess the "knowledge density" of a document chunk on a scale of 0-100.

## Evaluation Criteria
Score based on these factors:
1. **Actionable Knowledge (40%)**: Does it contain formulas, procedures, rules, or methods that can be directly applied?
2. **Technical Depth (30%)**: Does it contain domain-specific terminology, precise definitions, or quantitative analysis?
3. **Logical Structure (20%)**: Is the reasoning clear with cause-effect relationships, conditions, or decision logic?
4. **Practical Examples (10%)**: Are there concrete examples, case studies, or real-world applications?

## Chunk Information
- Path: {path_str}
- Content length: {len(chunk_content)} characters

## Chunk Content
```
{chunk_content[:30000]}
```

## Your Task
1. Analyze the chunk against each criterion
2. Provide a single overall score from 0-100
3. Higher scores = more valuable for knowledge extraction

## Output Format
Return ONLY a JSON object:
```json
{{"score": <0-100>, "reasoning": "<brief explanation in {OUTPUT_LANGUAGE}>"}}
```

Return ONLY the JSON object."""

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.3
                },
                timeout=60
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            # Parse score from response
            json_match = re.search(r'\{[^{}]*"score"\s*:\s*(\d+)[^{}]*\}', content)
            if json_match:
                return int(json_match.group(1))

            # Fallback: try to find any number
            num_match = re.search(r'\b(\d{1,3})\b', content)
            if num_match:
                return min(100, int(num_match.group(1)))

            return 50  # Default middle score

        except Exception as e:
            print(f"    Warning: LLM scoring failed: {e}")
            return 50


class SemanticDensityAnalyzer:
    """
    Main analyzer for semantic density scoring.

    Workflow:
    1. Load chunks from onion_peeler output
    2. Calculate NLP features (S_logic, S_entity, S_struct)
    3. Sample chunks for LLM gold scoring
    4. Calibrate weights via linear regression
    5. Apply weights to all chunks
    6. Generate heatmap output
    """

    def __init__(self, chunks_dir: str | Path):
        """
        Initialize analyzer.

        Args:
            chunks_dir: Path to onion_peeler output directory
        """
        self.chunks_dir = Path(chunks_dir)
        self.index_path = self.chunks_dir / "chunks_index.json"
        self.chunks_path = self.chunks_dir / "chunks"

        if not self.index_path.exists():
            raise FileNotFoundError(f"Chunks index not found: {self.index_path}")

        with open(self.index_path, encoding="utf-8") as f:
            self.chunk_index = json.load(f)

        self.nlp = NLPAnalyzer(language="auto")
        self.llm = DeepSeekR1Client()
        self.scores: list[ChunkScore] = []
        self.weights = {"w_logic": 1/3, "w_entity": 1/3, "w_struct": 1/3}

    def load_chunk_content(self, chunk_info: dict) -> str:
        """Load chunk content from file."""
        chunk_file = self.chunks_dir / chunk_info["file"]
        content = chunk_file.read_text(encoding="utf-8")
        # Remove YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        return content

    def analyze_all_chunks(self) -> list[ChunkScore]:
        """Calculate NLP scores for all chunks."""
        print(f"\n{'='*60}")
        print("Semantic Density Analysis")
        print(f"{'='*60}")
        print(f"Analyzing {len(self.chunk_index)} chunks...")
        print(f"Output language: {OUTPUT_LANGUAGE}")
        print()

        self.scores = []
        for i, chunk_info in enumerate(self.chunk_index):
            content = self.load_chunk_content(chunk_info)

            score = ChunkScore(
                chunk_id=chunk_info["id"],
                title=chunk_info["title"],
                parent_path=chunk_info.get("parent_path", []),
                book_index=chunk_info.get("book_index", i),  # Fallback to enumeration index
                start_line=chunk_info.get("start_line", 0),
                end_line=chunk_info.get("end_line", 0),
                content_preview=content[:200],
                token_count=chunk_info.get("tokens", len(content) // 2)
            )

            # Calculate NLP features
            score.s_logic = self.nlp.calc_s_logic(content)
            score.s_entity = self.nlp.calc_s_entity(content)
            score.s_struct = self.nlp.calc_s_struct(content)

            self.scores.append(score)

            if (i + 1) % 10 == 0 or i == len(self.chunk_index) - 1:
                print(f"  Processed {i + 1}/{len(self.chunk_index)} chunks")

        return self.scores

    def sample_for_calibration(self, n_samples: int = 15) -> list[ChunkScore]:
        """
        Sample chunks for LLM calibration.

        Uses stratified sampling based on NLP score distribution.
        """
        if not self.scores:
            self.analyze_all_chunks()

        # Calculate combined NLP score for stratification
        for score in self.scores:
            score.final_score = (score.s_logic + score.s_entity + score.s_struct) / 3

        # Sort by combined score and sample from different strata
        sorted_scores = sorted(self.scores, key=lambda x: x.final_score)
        n = len(sorted_scores)

        if n <= n_samples:
            return sorted_scores

        # Sample from different quantiles
        indices = []
        for i in range(n_samples):
            idx = int((i / (n_samples - 1)) * (n - 1)) if n_samples > 1 else 0
            indices.append(idx)

        # Add some randomness
        random.seed(42)
        for i in range(min(3, n_samples)):
            rand_idx = random.randint(0, n - 1)
            if rand_idx not in indices:
                indices[random.randint(0, len(indices) - 1)] = rand_idx

        return [sorted_scores[i] for i in sorted(set(indices))]

    def calibrate_weights(self, n_samples: int = 15) -> dict:
        """
        Calibrate weights using LLM gold scoring and linear regression.
        """
        print(f"\nCalibrating weights with {n_samples} samples...")

        samples = self.sample_for_calibration(n_samples)
        print(f"  Selected {len(samples)} samples for LLM scoring")

        # Get LLM gold scores
        X = []  # NLP features
        y = []  # Gold scores

        for i, score in enumerate(samples):
            print(f"  Scoring sample {i + 1}/{len(samples)}: {score.chunk_id}...")
            content = self.load_chunk_content(
                next(c for c in self.chunk_index if c["id"] == score.chunk_id)
            )
            gold = self.llm.score_chunk(content, score.title, score.parent_path)
            score.gold_score = gold

            X.append([score.s_logic, score.s_entity, score.s_struct])
            y.append(gold)

            print(f"    NLP: L={score.s_logic:.1f}, E={score.s_entity:.1f}, S={score.s_struct:.1f} → Gold: {gold}")

        # Linear regression
        X = np.array(X)
        y = np.array(y)

        reg = LinearRegression(fit_intercept=False, positive=True)
        reg.fit(X, y)

        # Normalize weights to sum to 1
        weights = reg.coef_
        weights = weights / weights.sum() if weights.sum() > 0 else np.array([1/3, 1/3, 1/3])

        self.weights = {
            "w_logic": float(weights[0]),
            "w_entity": float(weights[1]),
            "w_struct": float(weights[2])
        }

        print(f"\n  Calibrated weights:")
        print(f"    w_logic:  {self.weights['w_logic']:.4f}")
        print(f"    w_entity: {self.weights['w_entity']:.4f}")
        print(f"    w_struct: {self.weights['w_struct']:.4f}")

        return self.weights

    def apply_weights(self):
        """Apply calibrated weights to compute final scores."""
        for score in self.scores:
            score.final_score = (
                self.weights["w_logic"] * score.s_logic +
                self.weights["w_entity"] * score.s_entity +
                self.weights["w_struct"] * score.s_struct
            )

    def generate_heatmap_data(self) -> dict:
        """Generate heatmap data structure."""
        # Keep original book order using book_index
        ordered_scores = sorted(self.scores, key=lambda x: x.book_index)

        return {
            "metadata": {
                "total_chunks": len(self.scores),
                "weights": self.weights,
                "output_language": OUTPUT_LANGUAGE
            },
            "chunks": [s.to_dict() for s in ordered_scores],
            "statistics": {
                "mean_score": float(np.mean([s.final_score for s in self.scores])),
                "std_score": float(np.std([s.final_score for s in self.scores])),
                "max_score": float(max(s.final_score for s in self.scores)),
                "min_score": float(min(s.final_score for s in self.scores))
            }
        }

    def generate_heatmap_html(self, heatmap_data: dict) -> str:
        """Generate interactive HTML bar chart visualization showing density throughout the book."""
        chunks = heatmap_data["chunks"]
        stats = heatmap_data["statistics"]
        min_score = stats["min_score"]
        max_score = stats["max_score"]
        score_range = max_score - min_score if max_score > min_score else 1

        def get_gradient_color(score: float) -> str:
            """Convert score to gradient color from blue (low) to red (high)."""
            # Normalize to 0-1 range relative to min/max
            t = (score - min_score) / score_range
            t = max(0, min(1, t))  # Clamp to [0, 1]
            # Blue (0,100,255) -> Yellow (255,200,0) -> Red (255,50,50)
            if t < 0.5:
                # Blue to Yellow
                r = int(0 + (255 - 0) * (t * 2))
                g = int(100 + (200 - 100) * (t * 2))
                b = int(255 - (255 - 0) * (t * 2))
            else:
                # Yellow to Red
                r = 255
                g = int(200 - (200 - 50) * ((t - 0.5) * 2))
                b = int(0 + (50 - 0) * ((t - 0.5) * 2))
            return f"rgb({r}, {g}, {b})"

        # Generate HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knowledge Density Heatmap</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
        h1 {{ text-align: center; margin-bottom: 20px; color: #00d9ff; }}
        .stats {{ display: flex; justify-content: center; gap: 30px; margin-bottom: 30px; }}
        .stat {{ text-align: center; padding: 15px 25px; background: #16213e; border-radius: 10px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #00d9ff; }}
        .stat-label {{ font-size: 12px; color: #888; margin-top: 5px; }}
        .weights {{ text-align: center; margin-bottom: 30px; color: #888; font-size: 14px; }}
        .chart-container {{
            background: #16213e; border-radius: 10px; padding: 20px;
            margin: 0 auto; max-width: 1200px;
        }}
        .chart-title {{ text-align: center; margin-bottom: 15px; color: #888; font-size: 14px; }}
        .chart {{
            display: flex; align-items: flex-end; justify-content: center;
            height: 300px; gap: 2px; padding: 10px 0;
            border-bottom: 2px solid #333;
        }}
        .bar {{
            flex: 1; max-width: 25px; min-width: 8px;
            border-radius: 3px 3px 0 0;
            cursor: pointer; transition: opacity 0.2s, transform 0.2s;
            position: relative;
        }}
        .bar:hover {{ opacity: 0.8; transform: scaleY(1.02); }}
        .x-axis {{
            display: flex; justify-content: space-between;
            padding: 10px 0; color: #666; font-size: 11px;
        }}
        .y-axis {{
            position: absolute; left: 10px; top: 50%;
            transform: rotate(-90deg) translateX(-50%);
            color: #666; font-size: 12px;
        }}
        .tooltip {{
            position: fixed; max-width: 350px; padding: 15px;
            background: #0f0f23; border: 1px solid #00d9ff;
            border-radius: 8px; display: none; z-index: 1000;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }}
        .tooltip h3 {{ color: #00d9ff; margin-bottom: 10px; font-size: 14px; }}
        .tooltip p {{ margin: 5px 0; font-size: 12px; }}
        .legend {{
            display: flex; justify-content: center; align-items: center;
            gap: 10px; margin-top: 30px;
        }}
        .gradient-bar {{
            width: 200px; height: 20px; border-radius: 4px;
            background: linear-gradient(to right, rgb(0,100,255), rgb(255,200,0), rgb(255,50,50));
        }}
        .legend-label {{ color: #888; font-size: 12px; }}
        .mean-line {{
            position: absolute; left: 0; right: 0;
            border-top: 2px dashed rgba(0, 217, 255, 0.5);
            z-index: 10;
        }}
        .mean-label {{
            position: absolute; right: -45px; top: -8px;
            color: #00d9ff; font-size: 10px;
        }}
    </style>
</head>
<body>
    <h1>Knowledge Density Heatmap</h1>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{len(chunks)}</div>
            <div class="stat-label">Total Chunks</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['mean_score']:.1f}</div>
            <div class="stat-label">Mean Score</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['max_score']:.1f}</div>
            <div class="stat-label">Max Score</div>
        </div>
        <div class="stat">
            <div class="stat-value">{stats['min_score']:.1f}</div>
            <div class="stat-label">Min Score</div>
        </div>
    </div>

    <div class="weights">
        Weights: Logic={heatmap_data['metadata']['weights']['w_logic']:.2f},
        Entity={heatmap_data['metadata']['weights']['w_entity']:.2f},
        Struct={heatmap_data['metadata']['weights']['w_struct']:.2f}
    </div>

    <div class="chart-container">
        <div class="chart-title">Density Score Throughout the Book (Left = Beginning, Right = End)</div>
        <div class="chart" style="position: relative;">
"""
        # Add mean line
        mean_height_pct = ((stats['mean_score'] - min_score) / score_range) * 100 if score_range > 0 else 50
        html += f"""
            <div class="mean-line" style="bottom: {mean_height_pct}%;">
                <span class="mean-label">Mean: {stats['mean_score']:.1f}</span>
            </div>
"""

        # Add bars for each chunk in book order
        for i, chunk in enumerate(chunks):
            score = chunk['final_score']
            color = get_gradient_color(score)
            # Height as percentage of chart (relative to score range)
            height_pct = ((score - min_score) / score_range) * 100 if score_range > 0 else 50
            height_pct = max(5, height_pct)  # Minimum 5% height for visibility

            title_escaped = chunk['title'].replace('"', '&quot;').replace("'", "&#39;")
            preview_escaped = chunk['content_preview'][:100].replace('"', '&quot;').replace("'", "&#39;").replace('\n', ' ')

            html += f"""
            <div class="bar"
                 style="height: {height_pct}%; background: {color};"
                 data-index="{i}"
                 data-id="{chunk['chunk_id']}"
                 data-title="{title_escaped}"
                 data-score="{score:.1f}"
                 data-logic="{chunk['s_logic']:.1f}"
                 data-entity="{chunk['s_entity']:.1f}"
                 data-struct="{chunk['s_struct']:.1f}"
                 data-gold="{chunk['gold_score'] if chunk['gold_score'] else 'N/A'}"
                 data-preview="{preview_escaped}...">
            </div>
"""

        html += f"""
        </div>
        <div class="x-axis">
            <span>Chapter 1</span>
            <span>→ Book Progress →</span>
            <span>Chapter {len(chunks) // 5 if len(chunks) > 5 else len(chunks)}</span>
        </div>
    </div>

    <div class="legend">
        <span class="legend-label">Low ({min_score:.1f})</span>
        <div class="gradient-bar"></div>
        <span class="legend-label">High ({max_score:.1f})</span>
    </div>

    <div class="tooltip" id="tooltip"></div>

    <script>
        const tooltip = document.getElementById('tooltip');
        document.querySelectorAll('.bar').forEach(bar => {{
            bar.addEventListener('mouseenter', (e) => {{
                const rect = bar.getBoundingClientRect();
                tooltip.innerHTML = `
                    <h3>#${{parseInt(bar.dataset.index) + 1}}: ${{bar.dataset.title}}</h3>
                    <p><strong>Score:</strong> ${{bar.dataset.score}}</p>
                    <p><strong>Logic:</strong> ${{bar.dataset.logic}} | <strong>Entity:</strong> ${{bar.dataset.entity}} | <strong>Struct:</strong> ${{bar.dataset.struct}}</p>
                    <p><strong>Gold:</strong> ${{bar.dataset.gold}}</p>
                    <p style="color: #888; margin-top: 8px;">${{bar.dataset.preview}}</p>
                `;
                tooltip.style.display = 'block';
                tooltip.style.left = Math.min(rect.left, window.innerWidth - 370) + 'px';
                tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + 'px';
                if (parseInt(tooltip.style.top) < 10) {{
                    tooltip.style.top = (rect.bottom + 10) + 'px';
                }}
            }});
            bar.addEventListener('mouseleave', () => {{
                tooltip.style.display = 'none';
            }});
        }});
    </script>
</body>
</html>
"""
        return html

    def analyze(self, n_calibration_samples: int = 15) -> dict:
        """
        Run full analysis pipeline.

        Returns:
            Heatmap data dictionary
        """
        # Step 1: Calculate NLP scores
        self.analyze_all_chunks()

        # Step 2: Calibrate weights
        self.calibrate_weights(n_calibration_samples)

        # Step 3: Apply weights
        self.apply_weights()

        # Step 4: Generate heatmap data
        heatmap_data = self.generate_heatmap_data()

        print(f"\n{'='*60}")
        print("Analysis Complete!")
        print(f"{'='*60}")
        print(f"Total chunks: {len(self.scores)}")
        print(f"Mean score: {heatmap_data['statistics']['mean_score']:.2f}")
        print(f"Score range: {heatmap_data['statistics']['min_score']:.2f} - {heatmap_data['statistics']['max_score']:.2f}")

        return heatmap_data

    def save_results(self, output_dir: str | Path = None) -> Path:
        """Run analysis and save results."""
        if output_dir is None:
            output_dir = self.chunks_dir.parent / f"{self.chunks_dir.stem}_density"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run analysis
        heatmap_data = self.analyze()

        # Save JSON
        json_path = output_dir / "density_scores.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(heatmap_data, f, ensure_ascii=False, indent=2)
        print(f"\nJSON saved to: {json_path}")

        # Save HTML heatmap
        html_path = output_dir / "heatmap.html"
        html_content = self.generate_heatmap_html(heatmap_data)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Heatmap saved to: {html_path}")

        return output_dir


def main():
    """CLI entry point."""
    import sys

    if len(sys.argv) < 2:
        # Default to test chunks
        chunks_dir = "test_data/financial_statement_analysis_test1_output/full_chunks"
    else:
        chunks_dir = sys.argv[1]

    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    analyzer = SemanticDensityAnalyzer(chunks_dir)
    analyzer.save_results(output_dir)


if __name__ == "__main__":
    main()
