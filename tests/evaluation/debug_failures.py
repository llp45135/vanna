
import json
import asyncio
import os
import sys
import pandas as pd
from typing import Dict, Any

sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from vanna.legacy.remote import VannaDefault
from vanna.core.nl2dsl import NL2DSLMixin
from vanna.integrations.openai.llm import OpenAILlmService
from vanna.core.llm.models import LlmMessage, LlmRequest
from vanna.core.user.models import User
from vanna.dsl.schema import QueryDSL

# Reuse LocalVanna from evaluate_comparison
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
            "examples": [],
            "sql": [] 
        }
    
    def connect_to_sqlite(self, url: str, **kwargs):
        super().connect_to_sqlite(url, **kwargs)
        if not hasattr(self, 'engine'):
            from sqlalchemy import create_engine
            if '://' not in url:
                url = f"sqlite:///{url}"
            self.engine = create_engine(url)

def run_debug():
    MODEL = "qwen/qwen3-coder-30b"
    BASE_URL = "http://127.0.0.1:1234/v1"
    API_KEY = "lm-studio"
    
    vn = LocalVanna(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    db_path = os.path.join(os.path.dirname(__file__), '../../TicketDB/ticket.db')
    vn.connect_to_sqlite(db_path)
    
    data_path = os.path.join(os.path.dirname(__file__), '../data/golden_ticket_20.jsonl')
    
    target_ids = [12, 13]
    
    print(f"DEBUG ANALYSIS for IDs: {target_ids}")
    
    with open(data_path, 'r') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        idx = i + 1
        if idx not in target_ids:
            continue
            
        entry = json.loads(line)
        question = entry['question']
        expected_dsl = entry['expected_dsl']
        
        print(f"\n{'='*60}")
        print(f"ID [{idx}] Question: {question}")
        print(f"{'='*60}")
        
        # 1. Expected
        print(f"\n[EXPECTED]")
        print(f"DSL: {json.dumps(expected_dsl, indent=2)}")
        try:
            sql_exp = vn.compile_dsl(expected_dsl)
            print(f"SQL: {sql_exp}")
            df_exp = vn.run_sql(sql_exp)
            print(f"Rows: {len(df_exp)}")
            print(df_exp.head(3).to_string())
        except Exception as e:
            print(f"ERROR: {e}")
            df_exp = None
            
        # 2. Generated
        print(f"\n[GENERATED DSL]")
        try:
            dsl_gen = vn.generate_dsl(question)
            print(f"DSL: {json.dumps(dsl_gen, indent=2)}")
            sql_gen = vn.compile_dsl(dsl_gen)
            print(f"SQL: {sql_gen}")
            df_gen = vn.run_sql(sql_gen)
            print(f"Rows: {len(df_gen)}")
            print(df_gen.head(3).to_string())
        except Exception as e:
            print(f"ERROR: {e}")
            
        print("-" * 30)

if __name__ == "__main__":
    run_debug()
