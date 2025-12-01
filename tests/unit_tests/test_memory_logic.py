import pytest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


os.environ["SELLY_MAX_HISTORY_TURNS"] = "12"
os.environ["SELLY_MAX_CONTEXT_TOKENS"] = "8000"
os.environ["SELLY_SUMMARIZE_AFTER_TURNS"] = "8"
os.environ["AZURE_OPENAI_MODEL"] = "gpt-35-turbo"

from app import extract_memory_from_user_text, inject_memory_system_block
def test_extract_plz_and_usage():
    """
    testing the extraction of plz and usage (verbrauch)
    """
    memory = {}
    user_input = "Meine Postleitzahl ist 12345, ich verbrauche 3500 kwh."

    extract_memory_from_user_text(user_input, memory)

    assert memory.get("plz") == "12345", "couldn't get PLZ"
    assert memory.get("verbrauch") == "3500", "couldn't get verbrauch"



def test_memory_injection_to_system_prompt():
    """
    testing the injection of memory to system prompt
    """
    memory = {"plz": "10115", "tarif": "Basis"}
    messages = [{"role": "user", "content": "Wie viel kostet?"}]

    new_messages = inject_memory_system_block(messages, memory)

    assert new_messages[0]["role"] == "system"
    assert "10115" in new_messages[0]["content"]
    assert "Basis" in new_messages[0]["content"]