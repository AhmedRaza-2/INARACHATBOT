from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from dotenv import load_dotenv
import google.generativeai as genai
import os
import uuid
import glob
from datetime import timedelta
from rag import RAGEngine
from auth import validate_user, register_user
from db_utils import get_all_sessions, log_message, get_context, create_session_if_missing

# === Load environment variables ===
load_dotenv()
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs")

# === Auto-detect context and QA dataset ===
def find_first_qa_and_summary():
    qa_files = glob.glob("outputs/*_qa.json")
    summary_files = glob.glob("outputs/*_summary.txt")

    if not qa_files or not summary_files:
        print("❌ No QA or summary files found in 'outputs/' folder.")
        return "", ""

    # Match files based on prefix
    qa_prefixes = {os.path.basename(f).replace("_qa.json", ""): f for f in qa_files}
    summary_prefixes = {os.path.basename(f).replace("_summary.txt", ""): f for f in summary_files}

    for prefix in qa_prefixes:
        if prefix in summary_prefixes:
            return qa_prefixes[prefix], summary_prefixes[prefix]

    print("❌ Could not find matching QA and summary file pair.")
    return "", ""

# === Load the context and init RAG ===
qa_dataset_path, summary_path = find_first_qa_and_summary()

if summary_path and os.path.exists(summary_path):
    with open(summary_path, "r", encoding="utf-8") as f:
        company_context = f.read().strip()
else:
    company_context = ""

rag = RAGEngine(qa_dataset_path) if qa_dataset_path else None

# === Flask App ===
app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.permanent_session_lifetime = timedelta(days=7)

# === Gemini generation ===
def generate_gemini_response(user_query, retrieved_faqs, context):
    faqs_text = "\n".join([f"Q: {faq['question']}\nA: {faq['answer']}" for faq in retrieved_faqs])
    prompt = f"""
You are a helpful AI customer assistant for the company.

Company Overview:
{company_context}

Recent Conversation:
{context}

Relevant FAQs:
{faqs_text}

User: "{user_query}"

Respond in a clear, concise, and professional manner:
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
    mode = request.args.get("mode", "login")
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

    create_session_if_missing(user_id, session_id)
    log_message(user_id, session_id, "user", user_input)

    if not rag:
        return jsonify({'response': "RAG engine not loaded. Please try again later."})

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
    user_id = session['user_id']
    return jsonify(get_all_sessions(user_id))

@app.route('/session/<session_id>')
def get_session_messages(session_id):
    if 'user_id' not in session:
        return jsonify([])
    from db_utils import get_messages_for_session
    return jsonify(get_messages_for_session(session['user_id'], session_id))

@app.route('/sessions', methods=['GET'])
def sessions_api():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    sessions_data = get_all_sessions(session['user_id'])
    return jsonify([
        {
            "session_id": s["session_id"],
            "title": s.get("title", "Untitled"),
            "started_at": s.get("started_at")
        }
        for s in sessions_data
    ])

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
    app.run(debug=True, port=5001)
