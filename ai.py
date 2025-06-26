import google.generativeai as genai
import json

api_key = "AIzaSyCFz8nLkOQH6sDYYMQOoGHSZk0xjeTE2ok"
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

def test_ai():
    """Test the AI integration"""
    input_question = "what is AI?"

    template = f"""
You are a helpful assistant. Please provide a summary of the asked question in two to three lines inside a json format.
Question : {input_question}

Example Output:
```json
{{
    "summary": "This is a sample summary of the question."
}}
```
"""

    try:
        response = model.generate_content(template)
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '')
        response_json = json.loads(cleaned_text)
        print("✅ AI Test Successful!")
        print("Response:", response_json)
        print("Response type:", type(response_json))
        return True
    except Exception as e:
        print(f"❌ AI Test Failed: {e}")
        print("Response object:", response if 'response' in locals() else 'No response')
        return False

if __name__ == "__main__":
    test_ai()
