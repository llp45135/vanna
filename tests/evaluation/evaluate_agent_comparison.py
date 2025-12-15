"""
Agent-Enabled Comparison: NL2DSL vs Vanna SQL with Full Agent Features

This script enables:
1. allow_llm_to_see_data=True for intermediate SQL
2. Execution error correction loop
3. Fair semantic comparison
"""

import json
import asyncio
import os
import sys
import pandas as pd
import time
from typing import Dict, Any, Optional, Tuple

sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
from vanna.core.nl2dsl import NL2DSLMixin
from vanna.integrations.openai.llm import OpenAILlmService
from vanna.core.llm.models import LlmMessage, LlmRequest
from vanna.core.user.models import User


class AgentEnabledVanna(NL2DSLMixin, ChromaDB_VectorStore):
    """
    Vanna with full agent capabilities enabled:
    - Intermediate SQL for data exploration
    - Error correction loop
    """
    
    def __init__(self, model, base_url, api_key, config=None):
        chroma_config = config or {}
        chroma_config['path'] = os.path.join(os.path.dirname(__file__), '.chroma_agent_eval')
        ChromaDB_VectorStore.__init__(self, config=chroma_config)
        
        self.llm_service = OpenAILlmService(
            model=model,
            base_url=base_url,
            api_key=api_key
        )
        self.dialect = "SQLite"
        self._conn = None
        
    def submit_prompt(self, prompt, **kwargs) -> str:
        messages = []
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            messages = prompt
        
        llm_messages = []
        for p in messages:
            if isinstance(p, dict):
                llm_messages.append(LlmMessage(
                    role=p.get('role', 'user'),
                    content=p.get('content', '') or '', 
                    tool_call_id=p.get('tool_call_id'),
                    tool_calls=p.get('tool_calls')
                ))
            else:
                llm_messages.append(LlmMessage(
                    role=getattr(p, 'role', 'user'),
                    content=getattr(p, 'content', str(p)) or ''
                ))

        request = LlmRequest(
            messages=llm_messages,
            user=User(id="eval_user", email="eval@example.com"),
            temperature=0.0
        )
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            response = loop.run_until_complete(self.llm_service.send_request(request))
        else:
            response = loop.run_until_complete(self.llm_service.send_request(request))
            
        return response.content if response.content else ""
    
    def system_message(self, message: str) -> dict:
        return {"role": "system", "content": message}
    
    def user_message(self, message: str) -> dict:
        return {"role": "user", "content": message}
    
    def assistant_message(self, message: str) -> dict:
        return {"role": "assistant", "content": message}
        
    def get_related_training_data(self, question, **kwargs):
        ddl_list = self.get_related_ddl(question, **kwargs)
        doc_list = self.get_related_documentation(question, **kwargs)
        sql_list = self.get_similar_question_sql(question, **kwargs)
        
        return {
            "ddl": ddl_list,
            "documentation": doc_list,
            "examples": [{"question": s.get("question", ""), "dsl": {}} for s in sql_list] if sql_list else [],
            "sql": sql_list
        }
    
    def connect_to_sqlite(self, url: str, **kwargs):
        import sqlite3
        from sqlalchemy import create_engine
        
        if '://' not in url:
            self._conn = sqlite3.connect(url)
            self.run_sql = lambda sql: pd.read_sql(sql, self._conn)
            self.run_sql_is_set = True
            self.engine = create_engine(f"sqlite:///{url}")
        else:
            self.engine = create_engine(url)
            self.run_sql = lambda sql: pd.read_sql(sql, self.engine)
            self.run_sql_is_set = True

    def generate_sql_with_correction(self, question: str, max_retries: int = 2) -> Tuple[str, int]:
        """
        Generate SQL with error correction loop.
        
        Returns:
            Tuple of (final_sql, retry_count)
        """
        # First attempt with allow_llm_to_see_data=True
        sql = self.generate_sql(question, allow_llm_to_see_data=True)
        
        if not sql or not self.is_sql_valid(sql):
            return sql, 0
        
        for retry in range(max_retries):
            try:
                # Try to execute
                df = self.run_sql(sql)
                return sql, retry
            except Exception as e:
                # Execution failed - ask LLM to fix
                error_msg = str(e)
                print(f"    Retry {retry + 1}: Execution error - {error_msg[:50]}...")
                
                fix_prompt = [
                    self.system_message(
                        f"You are a SQLite expert. The following SQL query failed with an error. "
                        f"Please fix it and return ONLY the corrected SQL.\n\n"
                        f"Original Question: {question}\n"
                        f"Failed SQL: {sql}\n"
                        f"Error: {error_msg}\n\n"
                        f"Return only the corrected SQL query, nothing else."
                    ),
                    self.user_message("Please provide the corrected SQL.")
                ]
                
                response = self.submit_prompt(fix_prompt)
                sql = self.extract_sql(response)
                
                if not sql or not self.is_sql_valid(sql):
                    continue
        
        return sql, max_retries

    def generate_dsl_with_correction(self, question: str, max_retries: int = 2) -> Tuple[Dict, int]:
        """
        Generate DSL with execution-based correction loop.
        
        Returns:
            Tuple of (final_dsl, retry_count)
        """
        dsl = self.generate_dsl(question)
        
        for retry in range(max_retries):
            try:
                sql = self.compile_dsl(dsl)
                df = self.run_sql(sql)
                return dsl, retry
            except Exception as e:
                error_msg = str(e)
                print(f"    DSL Retry {retry + 1}: {error_msg[:50]}...")
                
                # For DSL, we can ask LLM to fix the DSL
                context = self.get_related_training_data(question)
                context_str = f"DDL: {context['ddl']}\nQuestion: {question}\nFailed DSL: {json.dumps(dsl)}\nError: {error_msg}"
                
                fix_prompt = [
                    self.system_message(
                        "You are a DSL expert. Fix the following DSL that caused an execution error. "
                        "Return ONLY the corrected JSON DSL, nothing else."
                    ),
                    self.user_message(context_str)
                ]
                
                response = self.submit_prompt(fix_prompt)
                
                try:
                    # Try to parse the fixed DSL
                    clean = response.replace("```json", "").replace("```", "").strip()
                    dsl = json.loads(clean)
                except:
                    continue
        
        return dsl, max_retries


def compare_dataframes_semantic(df1, df2):
    """Semantic equivalence comparison."""
    import numpy as np
    
    if df1 is None or df2 is None:
        return False, "One DF is None"
    if df1.empty and df2.empty:
        return True, "Both Empty"
    
    if len(df1) != len(df2):
        return False, f"Row count mismatch: {len(df1)} vs {len(df2)}"
    
    if len(df1.columns) != len(df2.columns):
        return False, f"Column count mismatch: {len(df1.columns)} vs {len(df2.columns)}"
    
    def normalize_df(df):
        df = df.copy()
        for col in df.columns:
            df[col] = df[col].astype(str).str.lower().str.strip()
        df.columns = range(len(df.columns))
        df = df.sort_values(by=list(df.columns)).reset_index(drop=True)
        return df
    
    try:
        df1_norm = normalize_df(df1)
        df2_norm = normalize_df(df2)
        
        from itertools import permutations
        
        if len(df1.columns) <= 4:
            for perm in permutations(range(len(df2_norm.columns))):
                df2_reordered = df2_norm[[*perm]].copy()
                df2_reordered.columns = df1_norm.columns
                df2_sorted = df2_reordered.sort_values(by=list(df2_reordered.columns)).reset_index(drop=True)
                if df1_norm.equals(df2_sorted):
                    return True, "Semantic Match"
        else:
            df2_norm.columns = df1_norm.columns
            df2_sorted = df2_norm.sort_values(by=list(df2_norm.columns)).reset_index(drop=True)
            if df1_norm.equals(df2_sorted):
                return True, "Semantic Match"
        
        # Numeric comparison
        try:
            nums1 = sorted([float(v) for col in df1.columns for v in df1[col] if str(v).replace('.','',1).replace('-','',1).isdigit()])
            nums2 = sorted([float(v) for col in df2.columns for v in df2[col] if str(v).replace('.','',1).replace('-','',1).isdigit()])
            
            if len(nums1) == len(nums2) and len(nums1) > 0:
                if all(abs(a - b) < 0.01 for a, b in zip(nums1, nums2)):
                    return True, "Numeric Match"
        except:
            pass
            
        return False, "Values Mismatch"
    except Exception as e:
        return False, f"Comparison Error: {e}"


def run_agent_comparison():
    MODEL = "qwen/qwen3-coder-30b"
    BASE_URL = "http://127.0.0.1:1234/v1"
    API_KEY = "lm-studio"
    
    print("=" * 70)
    print("AGENT-ENABLED COMPARISON: NL2DSL vs Vanna SQL with Full Features")
    print("=" * 70)
    print("\nFeatures enabled:")
    print("  ✓ allow_llm_to_see_data=True (intermediate SQL)")
    print("  ✓ Execution error correction loop (max 2 retries)")
    print("  ✓ Semantic equivalence comparison")
    
    print("\n1. Initializing Agent-Enabled Vanna...")
    vn = AgentEnabledVanna(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    
    db_path = os.path.join(os.path.dirname(__file__), '../../TicketDB/ticket.db')
    vn.connect_to_sqlite(db_path)
    
    # Train
    print("\n2. Training Vanna...")
    ddl = "CREATE TABLE sale_record0523 (train_date DATE, ticket_price INTEGER, region TEXT, ticket_no TEXT, ofiice_no TEXT, window_no INTEGER, sale_mode TEXT, from_station_name TEXT, to_station_name TEXT, seat_type_code TEXT, coach_no TEXT, distance INTEGER, train_no TEXT)"
    
    docs = [
        "The table 'sale_record0523' contains sales data.",
        "Use 'ticket_price' for sales amount.",
        "Use 'train_date' for any date related queries.",
        "Use 'ticket_no' for counting records.",
        "Use 'from_station_name' for departure station."
    ]
    
    example_sqls = [
        ("Top 3 stations by total sales", "SELECT from_station_name, SUM(ticket_price) as total_sales FROM sale_record0523 GROUP BY from_station_name ORDER BY total_sales DESC LIMIT 3"),
        ("Sales by year", "SELECT strftime('%Y', train_date) as year, SUM(ticket_price) as sales FROM sale_record0523 GROUP BY year"),
        ("Total sales", "SELECT SUM(ticket_price) as total_sales FROM sale_record0523"),
    ]
    
    vn.train(ddl=ddl)
    for doc in docs:
        vn.train(documentation=doc)
    for q, sql in example_sqls:
        vn.train(question=q, sql=sql)
    
    print("   Training complete!")
    
    # Run comparison
    print("\n3. Running Agent-Enabled Comparison...")
    data_path = os.path.join(os.path.dirname(__file__), '../data/golden_ticket_20.jsonl')
    
    results = []
    dsl_retries_total = 0
    sql_retries_total = 0
    
    with open(data_path, 'r') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if not line.strip():
            continue
            
        entry = json.loads(line)
        question = entry['question']
        expected_dsl = entry['expected_dsl']
        
        print(f"\n[{i+1}/{len(lines)}] Q: {question}")
        
        row = {"id": i+1, "question": question}
        
        # Ground Truth
        try:
            sql_truth = vn.compile_dsl(expected_dsl)
            df_truth = vn.run_sql(sql_truth)
        except Exception as e:
            print(f"  Ground Truth Error: {e}")
            df_truth = None

        # NL2DSL with correction
        df_dsl = None
        try:
            start = time.time()
            dsl, dsl_retries = vn.generate_dsl_with_correction(question)
            sql_dsl = vn.compile_dsl(dsl)
            row['dsl_time'] = time.time() - start
            row['dsl_retries'] = dsl_retries
            dsl_retries_total += dsl_retries
            df_dsl = vn.run_sql(sql_dsl)
            row['dsl_sql'] = sql_dsl
        except Exception as e:
            print(f"  DSL Error: {e}")

        # Vanna SQL with correction
        df_sql = None
        try:
            start = time.time()
            sql_vanna, sql_retries = vn.generate_sql_with_correction(question)
            row['sql_time'] = time.time() - start
            row['sql_retries'] = sql_retries
            sql_retries_total += sql_retries
            row['sql_sql'] = sql_vanna
            if sql_vanna and vn.is_sql_valid(sql_vanna):
                df_sql = vn.run_sql(sql_vanna)
        except Exception as e:
            print(f"  SQL Error: {e}")

        # Compare
        if df_truth is not None and df_dsl is not None:
            match, reason = compare_dataframes_semantic(df_truth.copy(), df_dsl.copy())
            row['dsl_vs_truth'] = match
            print(f"  DSL: {'✅' if match else '❌'}")
        
        if df_truth is not None and df_sql is not None:
            match, reason = compare_dataframes_semantic(df_truth.copy(), df_sql.copy())
            row['sql_vs_truth'] = match
            print(f"  SQL: {'✅' if match else '❌'}")
        
        results.append(row)

    # Summary
    df_results = pd.DataFrame(results)
    print("\n" + "=" * 70)
    print("RESULTS (Agent-Enabled)")
    print("=" * 70)
    
    dsl_acc = df_results['dsl_vs_truth'].mean() if 'dsl_vs_truth' in df_results else 0
    sql_acc = df_results['sql_vs_truth'].mean() if 'sql_vs_truth' in df_results else 0
    
    print(f"\nNL2DSL Accuracy: {dsl_acc:.2%} (retries: {dsl_retries_total})")
    print(f"Vanna SQL Accuracy: {sql_acc:.2%} (retries: {sql_retries_total})")
    
    out_path = "eval_agent_comparison_results.csv"
    df_results.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    run_agent_comparison()
