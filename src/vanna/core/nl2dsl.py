
import json
import logging
from typing import Optional, Dict, Any, List, Union
import pandas as pd
from pydantic import ValidationError

from vanna.dsl.schema import QueryDSL
from vanna.dsl.compiler import DSLCompiler
from vanna.dsl.errors import DSLValidationError, DSLCompileError

logger = logging.getLogger(__name__)

class NL2DSLMixin:
    """
    Mixin to add NL2DSL capabilities to a Vanna instance.
    Expected to be mixed into a class that has:
    - submit_prompt(prompt, **kwargs) -> str
    - get_related_training_data(question, **kwargs) -> dict
    - run_sql(sql, **kwargs) -> pd.DataFrame
    - run_sql_is_set -> bool (property)
    """

    def generate_dsl(self, question: str, auto_train: bool = True) -> Dict[str, Any]:
        """
        Generates DSL JSON from natural language.
        Includes retry logic for validation errors.
        """
        # 1. Retrieve Context
        context_data = self.get_related_training_data(question)
        ddl_list = context_data.get('ddl', [])
        doc_list = context_data.get('documentation', [])
        examples_list = context_data.get('examples', [])
        
        context_str = "Table Schema:\n" + "\n".join(ddl_list)
        if doc_list:
             context_str += "\n\nDocumentation:\n" + "\n".join(doc_list)
             
        if examples_list:
            context_str += "\n\nExamples:\n"
            for ex in examples_list:
                context_str += f"Q: {ex['question']}\nJSON: {json.dumps(ex['dsl'])}\n\n"
        
        # 2. Construct Prompt
        system_msg = (
            "You are a precise data engine. Your task is to convert the natural language question "
            "into a JSON DSL object based on the provided Table Schema.\n"
            "The JSON must conform strictly to this structure (Pydantic-like naming):\n"
            "QueryDSL(table: str, filters: list, aggregates: list, group_by: list, time_grains: list, sorts: list, limit: int)\n"
            "Filter(field, op, value). Aggregation(func, field, alias). TimeDimension(field, grain, alias).\n"
            "Rules:\n"
            "1. Return ONLY the JSON. No markdown formatting.\n"
            "2. Always ensure the 'table' field matches a table in the schema.\n"
            "3. ALIASING: Use meaningful aliases. For aggregations, use suffixes (e.g. '_sum', '_count', '_avg') or match the column name if unique.\n"
            "4. AGGREGATIONS: If the question implies a calculation (total, count, average), YOU MUST include an Aggregation. However, for 'List distinct' or 'Show distinct' questions, do NOT add a count aggregation unless asked.\n"
            "5. ENUMS: func must be one of [sum, avg, count, min, max, count_distinct]. op must be one of [eq, neq, gt, lt, gte, lte, in, not_in, like].\n"
            "6. SORTING: 'Top N' means ORDER BY metric DESC. 'Bottom N' or 'sorted ascending' means ORDER BY metric ASC. Do NOT use 'asc' for 'Top N'.\n"
            "7. TIME GRAINS: When using time_grains, the 'group_by' MUST contain the TIME GRAIN ALIAS (e.g. 'year'), NOT the raw column name. Example: if time_grains has alias='year', then group_by=['year'].\n"
            "8. LIMIT: Do NOT add a 'limit' unless the user explicitly asks for it (e.g. 'Top 10', 'First 5'). Default to no limit."
        )
        
        user_msg = f"Context:\n{context_str}\n\nQuestion: {question}"
        
        # 3. LLM Call (Attempt 1)
        prompt_messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]
        
        response = self.submit_prompt(prompt_messages)
        
        
        try:
            dsl = self._parse_and_validate_dsl(response)
            # Semantic Validation: Try to compile to catch hallucinations
            # This ensures we leverage the retry loop for invalid columns too.
            try:
                self.compile_dsl(dsl)
            except DSLCompileError as e:
                # Re-raise as ValidationError to trigger the retry logic below
                raise DSLValidationError(f"Semantic Error: {str(e)}")
            return dsl

        except (ValidationError, DSLValidationError, json.JSONDecodeError) as e:
            logger.warning(f"DSL Generation failed (Attempt 1): {e}. Retrying...")
            
            # 4. Retry Logic (FR-005)
            # Feed error back to LLM
            retry_msg = (
                f"The previous output was invalid. Error: {str(e)}\n"
                "Please fix the JSON and return it again."
            )
            prompt_messages.append({"role": "assistant", "content": response})
            prompt_messages.append({"role": "user", "content": retry_msg})
            
            response_retry = self.submit_prompt(prompt_messages)
            
            # If fail again, raise exception
            dsl_retry = self._parse_and_validate_dsl(response_retry)
            # Optional: We could validate semantics again here, but if it fails twice, we just let it crash/fail as intended.
            # But strictly, we should probably check semantics again to be consistent?
            # Or just return it and let compile_dsl fail later.
            # FR-005 says "Retry Once".
            return dsl_retry

    def _parse_and_validate_dsl(self, llm_response: str) -> Dict[str, Any]:
        """
        Parses string response to JSON and validates against Pydantic schema.
        """
        # Clean markdown code blocks if present
        clean_response = llm_response.strip()
        if clean_response.startswith("```"):
            clean_response = clean_response.split("```")[1]
            if clean_response.startswith("json"):
                clean_response = clean_response[4:]
        clean_response = clean_response.strip()
        
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError as e:
             raise DSLValidationError(f"Invalid JSON format: {e}")

        try:
            # Validate with Pydantic
            validated = QueryDSL(**data)
            return validated.model_dump() # Return dict
        except ValidationError as e:
            raise DSLValidationError(f"Schema Validation Error: {e}")

    def compile_dsl(self, dsl: Dict[str, Any], metadata: Any = None) -> str:
        """
        Compiles valid DSL dictionary into SQL string.
        
        Args:
            dsl: The DSL dictionary to compile.
            metadata: Optional SQLAlchemy MetaData. If not provided, 
                      it will be reflected from the connected engine.
        
        Returns:
            Executable SQL string.
            
        Raises:
            DSLCompileError: For semantic issues (e.g. invalid column).
            DSLValidationError: If DSL structure is missing required fields.
        """
        # We need access to an SQLAlchemy MetaData object.
        # If passed explicitly, use it (Good for tests).
        if metadata is not None:
             # Assume it is populated MetaData
             pass
        else:
            if not hasattr(self, '_engine') and not hasattr(self, 'engine'):
                 raise DSLCompileError("No database engine found. Connect to database first or pass metadata.")
            
            engine = getattr(self, 'engine', getattr(self, '_engine', None))
            
            from sqlalchemy import MetaData
            metadata = MetaData()
            # Reflect specifically the table requested? Or all?
            # For performance, reflect the target table.
            dsl_table = dsl.get('table')
            if dsl_table:
                try:
                    metadata.reflect(bind=engine, only=[dsl_table])
                except Exception as e:
                     raise DSLCompileError(f"Could not reflect table '{dsl_table}': {e}")
            else:
                 raise DSLValidationError("DSL missing 'table' field.")
            
            dialect_name = engine.dialect.name

        # If metadata was passed, we need dialect?
        # If metadata passed, we assume simplistic dialect (sqlite) or need arg?
        # The API contract says `compile_dsl(dsl, metadata)`.
        # DSLCompiler needs dialect_name.
        # We can try to guess or default to sqlite if strictly metadata passed without engine.
        if not 'dialect_name' in locals():
             dialect_name = 'sqlite' # Default safe fallback

        compiler = DSLCompiler(metadata, dialect_name=dialect_name)
        return compiler.compile_to_str(QueryDSL(**dsl)) # Re-validate to object

    def run_nl2dsl(self, question: str) -> pd.DataFrame:
        """
        End-to-end NL2DSL execution.
        """
        # 1. Generate
        dsl_dict = self.generate_dsl(question)
        
        # 2. Compile
        sql = self.compile_dsl(dsl_dict)
        
        # 3. Execute
        # Reuse existing run_sql
        return self.run_sql(sql)
