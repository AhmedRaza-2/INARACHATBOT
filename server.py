
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from dotenv import load_dotenv
import google.generativeai as genai
import os
import uuid

from datetime import timedelta
from rag import RAGEngine
from auth import validate_user, register_user
from db_utils import log_message, get_context, get_all_sessions
from db_utils import log_message, get_context, create_session_if_missing, get_pakistan_time

# === Load environment variables ===
load_dotenv()

# === Configure Gemini API ===
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs")

# === Initialize Flask app ===
app = Flask(__name__, template_folder='templates')

app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.permanent_session_lifetime = timedelta(days=7)

# === Load RAG Engine with your data ===
rag = RAGEngine('inara_qa.json')

# === Company context for Gemini prompt ===
company_context = """Inara Technologies is a software/IT services company based in Islamabad, Pakistan.
They specialize in AI, enterprise tools, cloud, and automation. Clients range across the Middle East and South Asia."""

# === Gemini response builder ===
def generate_gemini_response(user_query, retrieved_faqs, context):
    faqs_text = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in retrieved_faqs])
    prompt = f"""
You are a helpful AI customer assistant for Inara Technologies.

Company Info:
{company_context}

Recent Conversation:
{context}

Relevant FAQs:
{faqs_text}

User: "{user_query}"

Respond helpfully:
"""
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini API Error:", e)
        return "Sorry, I couldn’t process that. Please try again later."


# === Routes ===
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['user_id'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    mode = request.args.get("mode", "login") # Default to login mode

    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")

        if mode == "signup":
            success, msg = register_user(username, password)
        else:
            success, msg = validate_user(username, password)

        if success:
            session.permanent = True
            session["user_id"] = username
            return redirect(url_for('home'))
        else:
            return render_template("login.html", error=msg, mode=mode)

    return render_template("login.html", mode=mode)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_input = data.get('message', '')
    session_id = data.get('session_id') or f"sess_{uuid.uuid4().hex[:8]}"
    user_id = session['user_id']

    # Ensure session exists
    create_session_if_missing(user_id, session_id)

    # Log message
    log_message(user_id, session_id, "user", user_input)

    # Retrieve FAQs
    retrieved_faqs = rag.retrieve_top_k(user_input, k=3)
    context = get_context(user_id, session_id)

    ai_response = generate_gemini_response(user_input, retrieved_faqs, context)

    log_message(user_id, session_id, "bot", ai_response)

    return jsonify({
        'response': ai_response,
        'session_id': session_id,
        'user_id': user_id
    })
@app.route('/sessions')
def get_sessions():
    if 'user_id' not in session:
        return jsonify([])

    from db_utils import get_all_sessions
    user_id = session['user_id']
    return jsonify(get_all_sessions(user_id))


@app.route('/session/<session_id>')
def get_session_messages(session_id):
    if 'user_id' not in session:
        return jsonify([])

    from db_utils import get_messages_for_session
    messages = get_messages_for_session(session['user_id'], session_id)
    return jsonify(messages)

@app.route('/sessions', methods=['GET'])
def sessions_api():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    sessions_data = get_all_sessions(session['user_id'])
    # Just return session_id and title
    result = [
        {
            "session_id": s["session_id"],
            "title": s.get("title", "Untitled"),
            "started_at": s.get("started_at")
        }
        for s in sessions_data
    ]
    return jsonify(result)

@app.route('/session/<session_id>/messages', methods=['GET'])
def session_messages(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = session['user_id']
    all_sessions = get_all_sessions(user)
    selected = next((s for s in all_sessions if s['session_id'] == session_id), None)

    if not selected:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(selected['messages'])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
