import asyncio
import os
import sys

# Ensure we can import vanna from src if not installed in site-packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from vanna.integrations.openai import OpenAILlmService
from vanna.core.llm import LlmRequest, LlmMessage
from vanna.core.user import User

async def test_lm_studio():
    print("Initializing OpenAILlmService...")
    try:
        llm = OpenAILlmService(
            model="qwen/qwen3-coder-30b",
            base_url="http://127.0.0.1:1234/v1",
            api_key="lm-studio"
        )
        
        print(f"Service initialized. Model: {llm.model}, Base URL: {llm._client.base_url}")
        
        # Create a simple request
        request = LlmRequest(
            messages=[
                LlmMessage(role="user", content="Say 'Hello, World!' if you can hear me.")
            ],
            user=User(id="test_user", email="test@example.com", group_memberships=[])
        )
        
        print("\nSending request to LM Studio...")
        response = await llm.send_request(request)
        
        print("\n=== Response Received ===")
        print(f"Content: {response.content}")
        print("=========================")
        print("\nSUCCESS: Connection to LM Studio is working!")
        
    except Exception as e:
        print(f"\nERROR: Failed to connect or get response.")
        print(f"Details: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_lm_studio())
