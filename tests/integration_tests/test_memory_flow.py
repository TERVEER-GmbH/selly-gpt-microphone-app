import sys
import os
import pytest
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) #look 3 level upper for app.py

os.environ["SELLY_MAX_HISTORY_TURNS"] = "12"
os.environ["SELLY_MAX_CONTEXT_TOKENS"] = "8000"
os.environ["SELLY_SUMMARIZE_AFTER_TURNS"] = "8"
os.environ["AZURE_OPENAI_MODEL"] = "gpt-4o"
os.environ["AZURE_SPEECH_KEY"] = "dummy_key"
os.environ["AZURE_SPEECH_REGION"] = "dummy_region"

from app import create_app

@pytest.mark.asyncio
async def test_conversation_endpoint_flow():
    """
    this test wakes the server up and control if there is any error sending a request to '/conversation'
    """
    app = create_app()

    app.cosmos_conversation_client = None
    app.cosmos_prompt_client = None

    #test client
    async with app.test_client() as client:

        payload = {
            "messages": [
                {"role": "user", "content": "Hallo, meine PLZ ist 10115 und ich verbrauche 2500 kwh."}
            ],
            "history_metadata": {
                "conversation_id": "test-integration-id-1",
                "memory": {}
            }
        }

        response = await client.post("/conversation", json=payload)

        assert response.status_code == 200, f"Error! Status Code: {response.status_code}"

        response_data = await response.get_data()
        assert len(response_data) > 0, "the answer from the server is empty!"

        print(f"\n Server answer (the first 100 chars): {response_data[:100]}...")
