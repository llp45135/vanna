# Column Meaning Inference Strategies

To tackle ambiguous column names (Pinyin/English abbreviations), we can combine **Data Sampling** and **Context Retrieval**. Here are 3 proposed solution architectures.

## Strategy 1: Data-Driven Inference (The "Sherlock" Approach)
*Best for: Cases where the data pattern is distinct (e.g., dates, prices, status codes).*

**Mechanism:**
1.  **Fetch Samples**: For every column, query 3-5 non-null distinct values.
2.  **LLM Pattern Matching**: Feed the column name + samples to the LLM.
3.  **Prompt Engineering**:
    > "Column `cz_date` contains `['2023-01-01', '2023-02-14']`. `cz` is likely Pinyin. What is this column?"
    > **AI Inference**: `cz` -> `chong zhi` (Recharge) or `cao zuo` (Operation). Given it's a date, likely "Operation Date" or "Recharge Date".

**Pros:** No external docs needed; catches actual data implementation.
**Cons:** Can be ambiguous (Is `1` "Active" or "Male"?).

## Strategy 2: Business Context RAG (The "Librarian" Approach)
*Best for: Large enterprises with existing (but messy) documentation.*

**Mechanism:**
1.  **Ingest Docs**: Users drop CSV/PDF/Markdown "Data Dictionary" files into a folder.
2.  **Vectorize**: Use Vanna's built-in vector store to index these chunks.
3.  **Retrieval**: When analyzing table `t_user`, search vector DB for "t_user schema" or "user fields".
4.  **Synthesis**: The LLM uses the retrieved definitions to decode `yhm` to "User Name".

**Pros:** High accuracy for specific domain logic.
**Cons:** Requires maintaining a document corpus.

## Strategy 3: Heuristic Pinyin Expansion + Feedback Loop
*Best for: Strongly adhered-to naming conventions (e.g., `xm` always means `xing ming`).*

**Mechanism:**
1.  **Pinyin Decoder**: Run column names through a Pinyin-to-Hanzi abbreviation library to get candidates (`xm` -> `xing ming`, `xiang mu`).
2.  **Semantic Ranking**: Use LLM to rank which candidate fits the *Table Context*. (In `Student` table, `xm` is Name; in `Project` table, `xm` is Project).
3.  **Human Verification**: Generate a "Suggestion" report (`confidence < 80%`) for user review.

## Recommended Implementation Plan
We can upgrade our `generate_report.py` to use a **Hybrid of Strategy 1 and 2**:

1.  Modify the script to **query `SELECT * LIMIT 5`** for each table.
2.  Add a `docs/` folder where you can place any reference markdown files.
3.  Update the Prompt to include both the **Sample Data** and any **Matching Docs**.

```python
# Pseudo-code for Hybrid Prompt
prompt = f"""
Analyze column `{col_name}`.
Samples: {sample_values}
Context from Docs: {retrieved_doc_chunks}

Task:
1. Decode the abbreviation (Pinyin/English).
2. Define the business meaning.
"""
```
