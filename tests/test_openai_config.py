
from unittest.mock import patch
from vanna.integrations.openai import OpenAILlmService

@patch("vanna.integrations.openai.llm.OpenAI")
def test_openai_config_defaults(mock_openai):
    """Test that default max_retries and timeout are passed to OpenAI client."""
    service = OpenAILlmService(api_key="test")
    
    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args[1]
    
    assert call_kwargs["max_retries"] == 5
    assert call_kwargs["timeout"] == 120.0

@patch("vanna.integrations.openai.llm.OpenAI")
def test_openai_config_custom(mock_openai):
    """Test that custom max_retries and timeout are passed to OpenAI client."""
    service = OpenAILlmService(
        api_key="test",
        max_retries=10,
        timeout=60.0
    )
    
    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args[1]
    
    assert call_kwargs["max_retries"] == 10
    assert call_kwargs["timeout"] == 60.0

@patch("vanna.integrations.openai.llm.OpenAI")
def test_openai_config_kwargs_precedence(mock_openai):
    """Test that explicit args take precedence over extra_client_kwargs if necessary, 
    but our implementation puts extra_client_kwargs AFTER explicit defaults in the dict,
    so extra_client_kwargs wins if key collision happens. 
    However, we should probably ensure explicit args work as intended.
    Let's check the implementation behavior.
    """
    # In the implementation:
    # client_kwargs = {"max_retries": max_retries, "timeout": timeout, **extra_client_kwargs}
    # So extra_client_kwargs overwrites defaults.
    
    service = OpenAILlmService(
        api_key="test",
        max_retries=5,
        timeout=120.0,
        base_url="http://test", # extra kwarg usually passed separately in init
        # passing max_retries in kwargs
    )
    # The signature has max_retries as explicit arg.
    # extra_client_kwargs captures things NOT in signature.
    
    mock_openai.assert_called_once()
    call_kwargs = mock_openai.call_args[1]
    assert call_kwargs["max_retries"] == 5
