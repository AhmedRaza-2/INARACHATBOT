from flask import Flask, request, jsonify, render_template
from rag import RAGEngine
import google.generativeai as genai
import uuid
from dotenv import load_dotenv
from db_utils import log_message, get_context

# === Load env vars ===
load_dotenv()

# === Gemini API ===
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs") 

app = Flask(__name__, template_folder='templates')
rag = RAGEngine('inara_qa.json')

company_context = """Inara Technologies is a software/IT services company based in Islamabad..."""

# === Gemini Prompt Builder ===
def generate_gemini_response(user_query, retrieved_faqs, context):
    faqs_text = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in retrieved_faqs])
    prompt = f"""
You are a helpful customer support assistant for Inara Technologies.

Company Info:
{company_context}

Conversation History:
{context}

Relevant FAQs:
{faqs_text}

User:
"{user_query}"

Now respond helpfully:
"""
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("🔥 Gemini API Error:", e)
        return "Sorry, I couldn’t process that. Please try again later."

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message', '')
    user_id = data.get('user_id') or "user_" + uuid.uuid4().hex[:6]
    session_id = data.get('session_id') or "sess_" + uuid.uuid4().hex[:6]

    # Save user message in MongoDB
    log_message(user_id, session_id, "user", user_input)

    # Use RAG to retrieve relevant FAQs
    retrieved_faqs = rag.retrieve_top_k(user_input, k=3)

    # Load previous chat context (from DB)
    context = get_context(user_id, session_id)

    # Generate response from Gemini
    ai_response = generate_gemini_response(user_input, retrieved_faqs, context)

    # Log bot response in MongoDB
    log_message(user_id, session_id, "bot", ai_response)

    return jsonify({
        'response': ai_response,
        'session_id': session_id,
        'user_id': user_id
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
