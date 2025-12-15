
import json
import asyncio
import os
import sys
import pandas as pd
import time
from typing import Dict, Any

# Ensure src is in path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from vanna.legacy.remote import VannaDefault
from vanna.core.nl2dsl import NL2DSLMixin
from vanna.integrations.openai.llm import OpenAILlmService
from vanna.core.llm.models import LlmMessage, LlmRequest
from vanna.core.user.models import User

class LocalVanna(NL2DSLMixin, VannaDefault):
    def __init__(self, model, base_url, api_key, config=None):
        super().__init__(model='dummy', api_key='dummy', config=config)
        self.llm_service = OpenAILlmService(
            model=model,
            base_url=base_url,
            api_key=api_key
        )
        
    def submit_prompt(self, prompt, **kwargs) -> str:
        messages = []
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            messages = prompt
        
        llm_messages = []
        for p in messages:
            llm_messages.append(LlmMessage(
                role=p.get('role', 'user'),
                content=p.get('content', '') or '', 
                tool_call_id=p.get('tool_call_id'),
                tool_calls=p.get('tool_calls')
            ))

        request = LlmRequest(
            messages=llm_messages,
            user=User(id="eval_user", email="eval@example.com"),
            temperature=0.0 # Deterministic
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
        
    def get_related_training_data(self, question, **kwargs):
        return {
            "ddl": [
                "CREATE TABLE sale_record0523 (train_date DATE, ticket_price INTEGER, region TEXT, ticket_no TEXT, ofiice_no TEXT, window_no INTEGER, sale_mode TEXT, from_station_name TEXT, to_station_name TEXT, seat_type_code TEXT, coach_no TEXT, distance INTEGER, train_no TEXT)",
            ],
            "documentation": [
                "The table 'sale_record0523' contains sales data.",
                "Use 'ticket_price' for sales amount.",
                "Use 'train_date' for any date related queries.",
                "Use 'ticket_no' for counting records.",
                "Use 'from_station_name' for departure station."
            ],
            "examples": [
                 {
                    "question": "Top 3 stations by total sales",
                    "sql": "SELECT from_station_name, SUM(ticket_price) as total_sales FROM sale_record0523 GROUP BY from_station_name ORDER BY total_sales DESC LIMIT 3",
                    "dsl": {} # Mock empty DSL to satisfy generate_dsl parser
                },
                {
                    "question": "Sales by year",
                    "sql": "SELECT strftime('%Y', train_date) as year, SUM(ticket_price) as sales FROM sale_record0523 GROUP BY year",
                    "dsl": {} # Mock empty DSL
                }
            ],
            "sql": [] 
        }
    
    def connect_to_sqlite(self, url: str, **kwargs):
        super().connect_to_sqlite(url, **kwargs)
        if not hasattr(self, 'engine'):
            from sqlalchemy import create_engine
            if '://' not in url:
                url = f"sqlite:///{url}"
            self.engine = create_engine(url)

    def generate_sql_manual(self, question: str) -> str:
        """
        Manually implement standard NL2SQL using the same context.
        """
        context = self.get_related_training_data(question)
        ddl = "\n".join(context['ddl'])
        docs = "\n".join(context['documentation'])
        examples = "\n".join([f"Q: {ex['question']}\nSQL: {ex['sql']}" for ex in context['examples']])
        
        system_msg = "You are a SQL expert. Convert the question to SQL for ANY SQLite database based on the Schema."
        user_msg = f"""
Schema:
{ddl}

Documentation:
{docs}

Examples:
{examples}

Question: {question}
SQL:"""
        
        response = self.submit_prompt([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ])
        
        # Simple extraction
        clean = response.replace("```sql", "").replace("```", "").strip()
        if clean.lower().startswith("select"):
            return clean
        # If it has text around it
        import re
        match = re.search(r"select.*", clean, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(0)
        return clean

def compare_dataframes(df1, df2):
    if df1 is None or df2 is None:
        return False, "One DF is None"
    if df1.empty and df2.empty:
        return True, "Both Empty"
    
    # 1. Normalize columns (lowercase)
    df1.columns = [str(c).lower() for c in df1.columns]
    df2.columns = [str(c).lower() for c in df2.columns]
    
    # 2. Check shape
    if df1.shape != df2.shape:
        return False, f"Shape mismatch: {df1.shape} vs {df2.shape}"
        
    # 3. Sort by first column for stability
    col1 = df1.columns[0]
    col2 = df2.columns[0]
    
    try:
        df1_s = df1.sort_values(by=col1).reset_index(drop=True)
        # Rename df2 cols to match df1 for comparison if they are same semantics
        df2.columns = df1.columns 
        df2_s = df2.sort_values(by=col1).reset_index(drop=True)
        
        # Loose numeric comparison
        import numpy as np
        # Check if values are close enough
        
        # Simple pandas equals first
        if df1_s.equals(df2_s):
            return True, "Exact Match"
            
        return False, "Content Mismatch"
    except Exception as e:
        return False, f"Comparison Error: {e}"

def run_comparison():
    MODEL = "qwen/qwen3-coder-30b"
    BASE_URL = "http://127.0.0.1:1234/v1"
    API_KEY = "lm-studio"
    
    print("Initializing Comparison Evaluator...")
    vn = LocalVanna(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    
    db_path = os.path.join(os.path.dirname(__file__), '../../TicketDB/ticket.db')
    if os.path.exists(db_path):
        vn.connect_to_sqlite(db_path)
    
    data_path = os.path.join(os.path.dirname(__file__), '../data/golden_ticket_20.jsonl')
    
    results = []
    
    print(f"Loading Golden Set: {data_path}")
    
    with open(data_path, 'r') as f:
        # Limit to 5 for quick dev test, or all? Let's do all.
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        entry = json.loads(line)
        question = entry['question']
        expected_dsl = entry['expected_dsl']
        
        print(f"\n[{i+1}/{len(lines)}] Q: {question}")
        
        row = {
            "id": i+1,
            "question": question,
            "dsl_gen_success": False,
            "dsl_exec_success": False,
            "sql_gen_success": False,
            "sql_exec_success": False,
            "match_expected": False,
            "methods_match": False
        }
        
        # --- 0. Ground Truth (from Expected DSL) ---
        try:
            sql_truth = vn.compile_dsl(expected_dsl)
            df_truth = vn.run_sql(sql_truth)
        except Exception as e:
            print(f"  Ground Truth Error: {e}")
            df_truth = None

        # --- 1. NL2DSL Approach ---
        sql_dsl = ""
        df_dsl = None
        try:
            start = time.time()
            dsl = vn.generate_dsl(question)
            sql_dsl = vn.compile_dsl(dsl)
            row['dsl_gen_time'] = time.time() - start
            row['dsl_gen_success'] = True
            row['dsl_sql'] = sql_dsl
            
            df_dsl = vn.run_sql(sql_dsl)
            row['dsl_exec_success'] = True
        except Exception as e:
            print(f"  DSL Error: {e}")
            row['dsl_error'] = str(e)

        # --- 2. Standard NL2SQL Approach ---
        sql_vanilla = ""
        df_vanilla = None
        try:
            start = time.time()
            # Use manual prompted method for fair comparison without vector store
            sql_vanilla = vn.generate_sql_manual(question)
            row['sql_gen_time'] = time.time() - start
            if sql_vanilla:
                row['sql_gen_success'] = True
                row['sql_sql'] = sql_vanilla
                
                df_vanilla = vn.run_sql(sql_vanilla)
                row['sql_exec_success'] = True
            else:
                row['sql_error'] = "No SQL generated"
        except Exception as e:
            print(f"  Vanilla SQL Error: {e}")
            row['sql_error'] = str(e)

        # --- Comparisons ---
        
        # DSL vs Truth
        if df_truth is not None and df_dsl is not None:
            match, msg = compare_dataframes(df_truth, df_dsl)
            row['dsl_vs_truth'] = match
            if match:
                print("  DSL: ✅ Matches Truth")
            else:
                print(f"  DSL: ❌ Mismatch ({msg})")
        
        # Vanilla vs Truth
        if df_truth is not None and df_vanilla is not None:
            match, msg = compare_dataframes(df_truth, df_vanilla)
            row['vanilla_vs_truth'] = match
            if match:
                print("  SQL: ✅ Matches Truth")
            else:
                print(f"  SQL: ❌ Mismatch ({msg})")
                
        # DSL vs Vanilla
        if df_dsl is not None and df_vanilla is not None:
             match, msg = compare_dataframes(df_dsl, df_vanilla)
             row['dsl_vs_vanilla'] = match
        
        results.append(row)

    # Summary
    df_results = pd.DataFrame(results)
    print("\n--- Comparative Summary ---")
    print(df_results[['id', 'dsl_vs_truth', 'vanilla_vs_truth', 'dsl_vs_vanilla']])
    
    dsl_acc = df_results['dsl_vs_truth'].mean()
    sql_acc = df_results['vanilla_vs_truth'].mean()
    
    print(f"\nDSL Accuracy: {dsl_acc:.2%}")
    print(f"SQL Accuracy: {sql_acc:.2%}")
    
    # Save results
    out_path = "eval_comparison_results.csv"
    df_results.to_csv(out_path, index=False)
    print(f"Saved details to {out_path}")

if __name__ == "__main__":
    run_comparison()
