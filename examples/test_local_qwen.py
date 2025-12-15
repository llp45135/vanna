
import asyncio
import os
import sys

# Ensure src is in path for local testing
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from vanna.legacy.remote import VannaDefault
from vanna.core.nl2dsl import NL2DSLMixin
from vanna.integrations.openai.llm import OpenAILlmService
from vanna.core.llm.models import LlmRequest

class LocalVanna(NL2DSLMixin, VannaDefault):
    def __init__(self, model, base_url, api_key, config=None):
        # Initialize VannaDefault (for SQLite connectivity)
        # We pass dummy values for remote model/api_key since we override submit_prompt
        super().__init__(model='dummy', api_key='dummy', config=config)
        
        # Initialize our custom LLM Service
        self.llm_service = OpenAILlmService(
            model=model,
            base_url=base_url,
            api_key=api_key
        )
        
    def connect_to_sqlite(self, url: str, **kwargs):
        # Override to ensure self.engine is set for NL2DSLMixin
        # VannaBase logic might store it elsewhere or just use a connection
        super().connect_to_sqlite(url, **kwargs)
        
        # In VannaBase, connect_to_sqlite usually sets 'run_sql' lambda.
        # But we need the SQLAlchemy engine for reflection.
        # Let's see if we can instantiate it if not present.
        if not hasattr(self, 'engine'):
            from sqlalchemy import create_engine
            # Vanna legacy might not use sqlalchemy for sqlite, but just sqlite3 lib?
            # If so, we need to make an engine for NL2DSL.
            if '://' not in url:
                url = f"sqlite:///{url}"
            self.engine = create_engine(url)

    def submit_prompt(self, prompt, **kwargs) -> str:
        """
        Synchronous wrapper for standard Vanna prompt submission,
        delegating to the async OpenAILlmService.
        """
        # Transform Vanna prompt structure (list of dicts or str) into LlmRequest
        messages = []
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            # Assumes Vanna's [{"role":..., "content":...}] format
            messages = prompt
        
        # We need to construct LlmRequest objects. 
        # But LlmRequest expects 'messages' as list of Message objects? 
        # Let's check LlmRequest definition.
        # OpenAILlmService._build_payload iterates request.messages.
        # request.messages should be list of objects with .role and .content attributes.
        
        from vanna.core.llm.models import LlmMessage, LlmRequest
        from vanna.core.user.models import User
        
        llm_messages = []
        for p in messages:
            llm_messages.append(LlmMessage(
                role=p.get('role', 'user'),
                content=p.get('content', '') or '', # content is required
                tool_call_id=p.get('tool_call_id'),
                tool_calls=p.get('tool_calls')
            ))

        request = LlmRequest(
            messages=llm_messages,
            user=User(id="dummy_user", email="dummy@example.com"), # User field is required
            temperature=0.0 # Deterministic for DSL
        )
        
        # Run async method synchronously
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # If we are already in a loop (e.g. jupyter), we might need nesting or just standard call?
            # For this script, we assume strict script execution.
            # But asyncio.run cannot be called when loop is running.
            # Simple hack for script:
            import nest_asyncio
            nest_asyncio.apply()
            response = loop.run_until_complete(self.llm_service.send_request(request))
        else:
            response = loop.run_until_complete(self.llm_service.send_request(request))
            
        return response.content if response.content else ""
        
    def get_related_training_data(self, question, **kwargs):
        """
        Mock implementation for retrieving context. 
        In a real app, this would query a vector DB.
        For this test, we return a static schema for the known ticket.db.
        """
        # We need to know the schema of TicketDB/ticket.db. 
        # Typically VannaBase has logic to get DDL if we 'trained' it.
        # But here we are manually running without training data in vector store.
        # We can fetch DDL from SQLite directly using inspection?
        # Or just hardcode for this specific test since we know the DB content?
        
        # Let's inspect what tables are in TicketDB.
        # Assuming we connected, we can use self.run_sql to get tables? 
        # But get_related_training_data is called BEFORE prompting.
        
        # Hardcoded for robustness in this specific manual test:
        return {
            "ddl": [
                "CREATE TABLE sale_record0523 (train_date DATE, ticket_price INTEGER, region TEXT)",
                # We inferred schema roughly. 
                # Let's prompt LLM to use this table for 'sales'.
            ],
            "documentation": [
                "The table 'sale_record0523' contains sales data. Use 'ticket_price' for sales amount and 'train_date' for the date."
            ],
            "sql": []
        }

def test_local_integration():
    # Configuration
    MODEL = "qwen/qwen3-coder-30b"
    BASE_URL = "http://127.0.0.1:1234/v1" 
    API_KEY = "lm-studio"
    DB_PATH = 'TicketDB/ticket.db'
    
    print(f"Initializing LocalVanna with model={MODEL}...")
    vn = LocalVanna(model=MODEL, base_url=BASE_URL, api_key=API_KEY)
    
    print(f"Connecting to SQLite: {DB_PATH}")
    vn.connect_to_sqlite(DB_PATH)
    
    question = "What are the total sales (ticket_price) by year (from train_date)?"
    
    print(f"\n--- Testing NL2DSL Flow ---")
    print(f"Question: {question}")
    
    try:
        # 1. Generate DSL only
        print("\n> Generating DSL...")
        dsl = vn.generate_dsl(question)
        print("Generated DSL:", dsl)
        
        # 2. Compile
        print("\n> Compiling to SQL...")
        sql = vn.compile_dsl(dsl)
        print("Generated SQL:", sql)
        
        # 3. Execute
        print("\n> Executing SQL...")
        df = vn.run_sql(sql)
        print("\nResult DataFrame:")
        print(df)
        
        print("\n✅ Test Passed!")
        
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_local_integration()
