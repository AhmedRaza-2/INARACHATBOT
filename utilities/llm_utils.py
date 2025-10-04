import google.generativeai as genai
import os
# Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

#def run_gemini(prompt):
 #   model = genai.GenerativeModel("gemini-2.0-flash")
 #  return model.generate_content(prompt).text.strip()

def run_gemini(prompt: str):
    model = genai.GenerativeModel("gemini-2.0-flash")

    # use streaming generator
    response = model.generate_content(
        prompt,
        stream=True
    )

    for chunk in response:
        if chunk.candidates and chunk.candidates[0].content.parts:
            yield chunk.candidates[0].content.parts[0].text


def generate_website_context(text):
    prompt = f"Summarize this website in 3–5 concise sentences: {text[:8000]}"
    try:
        ai_response = run_gemini(prompt)
    except Exception as e:
        print(f"Summary error: {e}")
        return "No summary available."
