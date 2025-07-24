import google.generativeai as genai

# Replace with your actual Gemini API key
genai.configure(api_key="AIzaSyAtJoxVJxwbkW1qpyCNOC4Ld38F1Zzi65E")

def test_gemini(prompt):
    model = genai.GenerativeModel("models/gemini-2.0-flash")
    response = model.generate_content(prompt)
    print("Gemini response:")
    print(response.text)

if __name__ == "__main__":
    test_prompt = "Summarize the key features of Python programming language."
    test_gemini(test_prompt)