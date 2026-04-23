import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

_client = genai.Client(api_key=GEMINI_API_KEY)


def generate_content(prompt: str, model_name: str = "gemini-3.1-flash-lite") -> str:
    response = _client.models.generate_content(model=model_name, contents=prompt)
    return response.text
