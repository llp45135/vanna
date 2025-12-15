"""
Evaluation and Loading utilities for NL2DSL.
"""
import json
from typing import List, Dict, Any

def load_golden_pairs(file_path: str) -> List[Dict[str, Any]]:
    """
    Loads Golden Q&A pairs from a JSONL file.
    Expected format per line:
    {"question": "...", "expected_dsl": {...}, "meta": ...}
    """
    pairs = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Validation? For MVP, just load.
                # Check required keys
                if "question" in data and "expected_dsl" in data:
                    pairs.append(data)
                else:
                    # Log warning?
                    pass 
            except json.JSONDecodeError:
                continue
    return pairs
