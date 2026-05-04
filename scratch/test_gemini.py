
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

def test_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"Testing Gemini with model: {model_name}")
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents="Hello, respond with 'SUCCESS' if you can read this."
        )
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_gemini()
