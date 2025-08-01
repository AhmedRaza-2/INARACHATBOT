from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import google.generativeai as genai
import os, time, json, re, uuid
from auth import validate_user, register_user
from rag import RAGEngine
from mongo_storage import (
    get_faqs as mongo_get_faqs, 
    save_chatbot_data, 
    get_summary, 
    get_title, 
    store_summary, 
    store_title, 
    store_faqs
)
from db_utils import (
    get_context, 
    log_message, 
    create_session_if_missing,
    get_all_sessions, 
    get_messages_for_session,
    create_session
)
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

genai.configure(api_key=os.getenv("GEMINI_API_KEY", "AIzaSyBPPbgz7iULDuRhY8y8UgbcrXoVepEWAbg"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")
visited = set()

# === Utility Functions ===

def clean_domain_name(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path
    domain = domain.replace("www.", "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    return cleaned.strip('_').lower()

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    return webdriver.Chrome(options=options)

def is_valid(url, base_domain):
    parsed = urlparse(url)
    return parsed.scheme in ["http", "https"] and base_domain in parsed.netloc

def extract_links(driver, base_url, base_domain):
    soup = BeautifulSoup(driver.page_source, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if is_valid(href, base_domain):
            links.add(href.split("#")[0].rstrip("/"))
    return links

def extract_visible_text(driver):
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except:
        return ""

def extract_title(driver):
    try:
        return driver.find_element(By.TAG_NAME, "title").get_attribute("innerText").replace("-", " ").strip()
    except:
        return "No Title"

def crawl_site(start_url, max_pages=300):
    base_domain = urlparse(start_url).netloc
    visited.clear()
    
    base_name = clean_domain_name(start_url)
    qa_path = os.path.join("outputs", base_name, f"{base_name}_qa.json")
    summary_path = os.path.join("outputs", base_name, f"{base_name}_summary.txt")
    title_path = os.path.join("outputs", base_name, f"{base_name}_title.txt")

    if os.path.exists(qa_path) and os.path.exists(summary_path):
        print(f"✅ Skipping crawl: data already exists for {start_url}")
        data = mongo_get_faqs(base_name)
        company_context = get_summary(base_name)
        title = get_title(base_name)
        combined_text = "\n\n".join([item["answer"] for item in data])
        return {start_url: combined_text}, title

    driver = setup_driver()
    to_visit, all_text = [start_url], {}
    extracted_title = ""

    try:
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue

            driver.get(url)
            time.sleep(2)
            if not extracted_title:
                extracted_title = extract_title(driver)

            text = extract_visible_text(driver)
            all_text[url] = text
            visited.add(url)
            to_visit.extend(link for link in extract_links(driver, url, base_domain)
                          if link not in visited and link not in to_visit)
    finally:
        driver.quit()

    return all_text, extracted_title

def convert_to_qa(text):
    prompt = f'''
You are a domain-agnostic AI assistant specialized in transforming raw text into structured knowledge.
Your task is to read the following input and generate a clean, diverse set of Question-Answer (Q&A) pairs.
Instructions:
- Generate at least 50 meaningful Q&A pairs.
- Cover all important points, facts, sections, or ideas in the text, including numbers.
- Rephrase questions naturally.
- Avoid vague or repetitive questions.
- Format the output as a JSON array:
[
  {{"question": "...", "answer": "..."}},
  ...
]
Text:
"""{text}"""
'''
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        res = model.generate_content(prompt)
        raw = res.text.strip()
        if raw.startswith("```json"):
            raw = raw[7:-3]
        return json.loads(raw)
    except Exception as e:
        print(f"Gemini error: {e}")
        return []

def generate_website_context(text):
    prompt = f"Summarize this website in 3–5 concise sentences: {text[:8000]}"
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        print(f"Summary error: {e}")
        return "No summary available."

def get_top_faqs(base_name, limit=4):
    try:
        faqs = mongo_get_faqs(base_name)
        return [item.get("question") for item in faqs[:limit]]
    except Exception as e:
        print(f"[FAQ ERROR] Failed to load FAQs for {base_name}: {e}")
        return []

# === Routes ===

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        email = request.form.get("email")

        if not url or not email:
            return render_template("url_input.html", error="Please provide both website URL and your email.", bot_name="bot")

        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "").lower()
        email_domain = email.split('@')[-1].lower()

        if email_domain != domain:
            return render_template(
                "url_input.html",
                error=f"Email domain ({email_domain}) must match website domain ({domain}).",
                bot_name="bot"
            )

        base_name = clean_domain_name(url)
        session['base_name'] = base_name
        session['user_email'] = email

        try:
            website_text, website_title = crawl_site(url)
            all_combined = "\n\n".join(website_text.values())
            qa_list = convert_to_qa(all_combined)
            summary_context = generate_website_context(all_combined)

            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode([item["question"] for item in qa_list], show_progress_bar=False)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(np.array(embeddings))

            save_chatbot_data(base_name, website_title, summary_context, qa_list, index)
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Crawl error: {e}")
            return render_template("url_input.html", error="Failed to process website.", bot_name="bot")

    return render_template("url_input.html", bot_name="bot")

@app.route('/homee')
def homee():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    base_name = session.get('base_name')
    if not base_name:
        return render_template("index.html", error="No website data found.", bot_name="bot")

    company_context = get_summary(base_name)
    try:
        rag = RAGEngine(base_name)
        rag_available = True
    except:
        rag_available = False

    return render_template(
        "index.html",
        username=session['user_id'],
        company_context=company_context,
        rag_available=rag_available,
        bot_name=base_name
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    base_name = session.get("base_name", "bot")
    mode = request.args.get("mode", "login")

    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        success, msg = (
            register_user(base_name, username, password) if mode == "signup" 
            else validate_user(base_name, username, password)
        )

        if success:
            session.permanent = True
            session["user_id"] = username
            return redirect(url_for('homee'))
        return render_template("login.html", error=msg, mode=mode, bot_name=base_name)

    return render_template("login.html", mode=mode, bot_name=base_name)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/greet', methods=['POST'])
def greet():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    user_id = session['user_id']
    session_id = request.json.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}"

    try:
        is_new = create_session_if_missing(base_name, user_id, session_id)
        messages = []

        if is_new:
            create_session(user_id, session_id, base_name)
            greeting = "👋 Hi! I'm your assistant for this website. How may I help you today?"
            messages.append({"type": "bot", "text": greeting})
            log_message(base_name, user_id, session_id, "bot", greeting)

            # Get FAQs for frontend display but DON'T create a separate message
            faqs = get_top_faqs(base_name)
            
            # Remove these lines that create the second message:
            # if faqs:
            #     faq_text = "Here are some common questions you can ask:\n" + "\n".join(f"• {q}" for q in faqs)
            #     messages.append({"type": "bot", "text": faq_text})
            #     log_message(base_name, user_id, session_id, "bot", faq_text)

            return jsonify({
                'messages': messages,
                'session_id': session_id,
                'greeted': True,
                'faqs': faqs  # Send FAQs for frontend to display as buttons
            })

        return jsonify({'greeted': False, 'session_id': session_id})
    except Exception as e:
        print(f"Greet error: {e}")
        return jsonify({'error': 'Failed to process greeting'}), 500

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    data = request.json
    user_input = data.get('message', '')
    session_id = data.get('session_id') or f"sess_{uuid.uuid4().hex[:8]}"
    user_id = session['user_id']

    try:
        rag = RAGEngine(base_name)
        if not rag.questions:
            return jsonify({'response': 'No data found for this domain.'}), 404

        retrieved_faqs = rag.retrieve_top_k(user_input, k=3)
        summary_context = get_summary(base_name) or ""
        context = get_context(base_name, user_id, session_id)

        prompt = f"Company: {summary_context}\nFAQs: {retrieved_faqs}\nContext: {context}\nUser: {user_input}"

        is_new = create_session_if_missing(base_name, user_id, session_id)
        if is_new:
            create_session(user_id, session_id, base_name)
            greeting_msg = "👋 Hi! I'm your assistant for this website. How may I help you today?"
            log_message(base_name, user_id, session_id, "bot", greeting_msg)

        model = genai.GenerativeModel("gemini-2.0-flash")
        ai_response = model.generate_content(prompt).text.strip()

        log_message(base_name, user_id, session_id, "user", user_input)
        log_message(base_name, user_id, session_id, "bot", ai_response)

        return jsonify({
            'response': ai_response,
            'session_id': session_id,
            'user_id': user_id,
            'greeted': is_new
        })
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'response': 'An error occurred while processing your request.'}), 500

@app.route('/get_faqs', methods=['POST'])
def get_faqs_route():
    base_name = session.get('base_name')
    if not base_name:
        return jsonify({"faqs": [], "error": "No base_name found"}), 400

    try:
        faqs = mongo_get_faqs(base_name)
        top_faqs = [item['question'] for item in faqs[:3]]
        return jsonify({"faqs": top_faqs})
    except Exception as e:
        print(f"FAQ error: {e}")
        return jsonify({"faqs": [], "error": str(e)}), 500

@app.route('/sessions')
def get_sessions():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    try:
        return jsonify(get_all_sessions(base_name, session['user_id']))
    except Exception as e:
        print(f"Sessions error: {e}")
        return jsonify({'error': 'Failed to fetch sessions'}), 500

@app.route('/session/<session_id>')
def get_session_messages(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    try:
        messages = get_messages_for_session(base_name, session['user_id'], session_id)
        return jsonify(messages)
    except Exception as e:
        print(f"Session messages error: {e}")
        return jsonify({'error': 'Failed to fetch session messages'}), 500

@app.route('/session/<session_id>/messages', methods=['GET'])
def session_messages(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    try:
        sessions = get_all_sessions(base_name, session['user_id'])
        session_data = next((s for s in sessions if s['session_id'] == session_id), None)
        if not session_data:
            return jsonify({'error': 'Session not found'}), 404

        messages = get_messages_for_session(base_name, session['user_id'], session_id)
        return jsonify(messages)
    except Exception as e:
        print(f"Session messages error: {e}")
        return jsonify({'error': 'Failed to fetch session messages'}), 500

# === Run App ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)