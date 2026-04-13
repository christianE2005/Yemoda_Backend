import os

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)


def get_gemini_model(model_name: str = "gemini-1.5-flash") -> genai.GenerativeModel:
    return genai.GenerativeModel(model_name)
