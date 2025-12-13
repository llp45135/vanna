import asyncio
import os
import sys
import pandas as pd

# Ensure local source is used
current_dir = os.getcwd()
src_path = os.path.abspath(os.path.join(current_dir, "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from vanna import Agent, AgentConfig
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.sqlite import SqliteRunner
from vanna.tools import RunSqlTool
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.integrations.local.agent_memory import DemoAgentMemory

# --- Configuration ---
DB_PATH = "./Chinook.sqlite"
CACHE_DIR = "analysis_cache"
FINAL_REPORT_FILE = "schema_report.md"

# --- Components Setup ---
class LocalUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="local_admin", email="admin@localhost", group_memberships=['admin'])

# Initialize proper components
llm = OpenAILlmService(
    model="qwen/qwen3-coder-30b",
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio"
)

tools = ToolRegistry()
# Ensure DB exists
if not os.path.exists(DB_PATH):
    print(f"Error: Database {DB_PATH} not found. Please run the notebook first to download it.")
    sys.exit(1)

sql_runner = SqliteRunner(database_path=DB_PATH)
tools.register_local_tool(RunSqlTool(sql_runner=sql_runner), access_groups=['admin'])
agent_memory = DemoAgentMemory()

agent = Agent(
    llm_service=llm,
    tool_registry=tools,
    user_resolver=LocalUserResolver(),
    config=AgentConfig(), # Default config
    agent_memory=agent_memory
)

async def ask_agent(prompt: str) -> str:
    """Helper to send a message to the agent and get the text response."""
    request_context = RequestContext()
    response_text = ""
    try:
        async for component in agent.send_message(request_context, prompt):
            if hasattr(component, 'rich_component') and component.rich_component:
                if hasattr(component.rich_component, 'content'):
                    content = str(component.rich_component.content)
                    print(".", end="", flush=True)
                    response_text += content
            elif hasattr(component, 'simple_component') and component.simple_component:
                 # Optional: print(component.simple_component.text)
                 pass
    except Exception as e:
        print(f"\nError interacting with agent: {e}")
        return ""
    
    return response_text

async def main():
    print(f"Starting analysis on {DB_PATH}...")
    os.makedirs(CACHE_DIR, exist_ok=True)

    # --- Step 1: Discover Tables ---
    print("\n[Step 1/4] Discovering Tables...")
    try:
        from vanna.capabilities.sql_runner import RunSqlToolArgs
        
        args = RunSqlToolArgs(sql="SELECT name FROM sqlite_master WHERE type='table';")
        dummy_context = RequestContext() # Can serve as tool context basics
        
        # run_sql is async and needs args object and context
        tables_df = await sql_runner.run_sql(args, dummy_context)
        
        tables = tables_df['name'].tolist()
        print(f"Found {len(tables)} tables: {tables}")
    except Exception as e:
        print(f"Error executing discovery SQL: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- Step 2: Incremental Analysis ---
    print("\n[Step 2/4] Analyzing Tables (Incremental)...")
    table_summaries = []

    for table in tables:
        cache_file = os.path.join(CACHE_DIR, f"{table}.md")
        
        if os.path.exists(cache_file):
            print(f"  -> {table}: Using cached analysis.")
            with open(cache_file, "r") as f:
                table_summaries.append(f.read())
            continue
            
        print(f"  -> {table}: Analyzing", end="")
        
        prompt = f"""
        Analyze the table `{table}`.
        1. List its columns and data types.
        2. Identify Primary Keys and Foreign Keys.
        3. Describe what data this table likely holds.
        4. Do NOT verify with SQL, just provide the analysis based on standard patterns or if you run SQL, run `PRAGMA table_info({table})` directly.
        
        Output valid Markdown.
        """
        
        analysis = await ask_agent(prompt)
        
        if analysis:
            with open(cache_file, "w") as f:
                f.write(analysis)
            table_summaries.append(analysis)
            print(" [Done]")
        else:
            print(" [Failed to get response]")

    # --- Step 3: Global Analysis ---
    print("\n[Step 3/4] Generating Executive Summary & ER Diagram...")
    
    # Context window management: If too many tables, might need to summarize the summaries.
    # For now, we assume they fit.
    combined_text = "\n\n".join(table_summaries)
    
    executive_prompt = f"""
    Here are the detailed schema definitions for all tables in the database:
    
    {combined_text[:50000]} # Truncate if purely massive, but ideally we pass it all
    
    Based on the above, generate:
    1. **Executive Summary**: Overview of the domain.
    2. **Entity-Relationship Diagram**: Use Mermaid JS syntax.
    3. **Data Integrity Suggestions**.
    
    Output ONLY Markdown.
    """
    
    print("  -> Asking Agent for high-level report...")
    executive_part = await ask_agent(executive_prompt)

    # --- Step 4: Final Assembly ---
    print("\n[Step 4/4] Assembling Final Report...")
    
    final_report = f"""# Database Schema Analysis Report

{executive_part}

## Table Details

"""
    for table, summary in zip(tables, table_summaries):
        final_report += f"### Table: {table}\n\n{summary}\n\n---\n\n"
        
    with open(FINAL_REPORT_FILE, "w") as f:
        f.write(final_report)
        
    print(f"\nSUCCESS: Report generated at {os.path.abspath(FINAL_REPORT_FILE)}")

if __name__ == "__main__":
    asyncio.run(main())
