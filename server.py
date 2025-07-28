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
from email.mime.text import MIMEText
global  base_name

from db_utils import (
    get_context, log_message, create_session_if_missing,
    get_all_sessions, get_messages_for_session,
)

from auth import validate_user, register_user

genai.configure(api_key="AIzaSyAtJoxVJxwbkW1qpyCNOC4Ld38F1Zzi65E")

app = Flask(__name__)
app.secret_key = "supersecretkey"
visited = set()

# === Utility Functions ===

def clean_domain_name(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path  # handles malformed URLs
    domain = domain.replace("www.", "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '_', domain)  # remove all non-alphanum chars
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
    visited.clear()  # Clear visited before new crawl
    
    output_dir = os.path.join("outputs", base_domain)
    qa_path = os.path.join(output_dir, f"{base_domain}_qa.json")
    summary_path = os.path.join(output_dir, f"{base_domain}_summary.txt")
    title_path = os.path.join(output_dir, f"{base_domain}_title.txt")

    if os.path.exists(qa_path) and os.path.exists(summary_path):
        print(f"✅ Skipping crawl: data already exists for {start_url}")

        # Load saved data
        with open(qa_path, "r", encoding="utf-8") as f:
            qa_data = json.load(f)

        with open(summary_path, "r", encoding="utf-8") as f:
            summary_text = f.read()

        with open(title_path, "r", encoding="utf-8") as f:
            title = f.read()

        # Convert back to raw site text (simulate for downstream code)
        combined_text = "\n\n".join([item["answer"] for item in qa_data])
        return {start_url: combined_text}, title
    driver = setup_driver()
    base_domain = urlparse(start_url).netloc
    to_visit, all_text = [start_url], {}
    extracted_title = ""

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue

        try:
            driver.get(url)
            time.sleep(2)
            if not extracted_title:
                extracted_title = extract_title(driver)

            text = extract_visible_text(driver)
            all_text[url] = text
            visited.add(url)
            to_visit.extend(link for link in extract_links(driver, url, base_domain)
                            if link not in visited and link not in to_visit)
        except:
            continue

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
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        res = model.generate_content(prompt)
        raw = res.text.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        return json.loads(raw)
    except Exception as e:
        print("Gemini error:", e)
        return []

def generate_website_context(text):
    prompt = f"Summarize this website in 3–5 concise sentences: {text[:8000]}"
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        return model.generate_content(prompt).text.strip()
    except:
        return "No summary available."

def find_qa_and_summary_for_domain(base_name):
    folder = os.path.join("outputs", base_name)
    return (
        os.path.join(folder, f"{base_name}_qa.json") if os.path.exists(os.path.join(folder, f"{base_name}_qa.json")) else "",
        os.path.join(folder, f"{base_name}_summary.txt") if os.path.exists(os.path.join(folder, f"{base_name}_summary.txt")) else ""
    )

def get_top_faqs(domain, limit=4):
    try:
        qa_path = f"outputs/{domain}_qa.json"
        if not os.path.exists(qa_path):
            return []

        with open(qa_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = [item.get("question") for item in data if item.get("question")]
        return questions[:limit]

    except Exception as e:
        print(f"[FAQ ERROR] Failed to load FAQs for {domain}: {e}")
        return []


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        email = request.form.get("email")

        if not url or not email:
            return "Please provide both website URL and your email."

        # Extract base domain from URL (e.g. https://www.example.com → example.com)
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "").lower()

        # Extract domain from email (e.g. user@example.com → example.com)
        email_domain = email.split('@')[-1].lower()

        if email_domain != domain:
            return f"""
            ❌ You must use an email from the same domain as the website.<br>
            Your email domain: <b>{email_domain}</b><br>
            Website domain: <b>{domain}</b>
            """

        # Email verified successfully
        base_name = domain  # use domain as folder name
        session['base_name'] = base_name  
        session['user_email'] = email

        folder_path = os.path.join("outputs", base_name)
        os.makedirs(folder_path, exist_ok=True)

        qa_path = os.path.join(folder_path, f"{base_name}_qa.json")
        summary_path = os.path.join(folder_path, f"{base_name}_summary.txt")
        title_path = os.path.join(folder_path, f"{base_name}_title.txt")

        if os.path.exists(qa_path) and os.path.exists(summary_path) and os.path.exists(title_path):
            print(f"✅ Skipping crawl: data already exists for {url}")
            return redirect(url_for('login'))

        # Crawl + generate data
        website_text, website_title = crawl_site(url)
        all_combined = "\n\n".join(website_text.values())
        qa_list = convert_to_qa(all_combined)
        summary_context = generate_website_context(all_combined)

        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(qa_list, f, indent=2)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_context)
        with open(title_path, "w", encoding="utf-8") as f:
            f.write(website_title)

        return redirect(url_for('login'))

    return render_template("url_input.html", bot_name="bot")

@app.route('/homee')
def homee():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    base_name = session.get('base_name')
    if not base_name:
        return "No website data found. Please generate data first."

    qa_dataset_path, summary_path = find_qa_and_summary_for_domain(base_name)
    
    faiss_path = os.path.join("outputs", base_name, f"{base_name}_index.faiss")

    if summary_path and os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            company_context = f.read().strip()
    else:
        company_context = ""

    rag = RAGEngine(qa_dataset_path,faiss_path) if qa_dataset_path else None

    return render_template(
        "index.html",
        username=session['user_id'],
        company_context=company_context,
        rag_available=rag is not None,
        bot_name=base_name
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    mode = request.args.get("mode", "login")
    base_nam = session.get("base_name")
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        if mode == "signup":
            success, msg = register_user(base_nam, username, password)
        else:
            success, msg = validate_user(base_nam, username, password)

        if success:
            session.permanent = True
            session["user_id"] = username
            return redirect(url_for('homee'))
        else:
            return render_template("login.html", error=msg, mode=mode,bot_name=base_nam)
    return render_template("login.html", mode=mode,bot_name=base_nam)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/greet', methods=['POST'])
def greet():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    user_id = session['user_id']
    session_id = request.json.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}"

    is_new = create_session_if_missing(base_name, user_id, session_id)

    messages = []

    if is_new:
        greeting = "👋 Hi! I'm your assistant for this website. How may I help you today?"
        messages.append({"type": "bot", "text": greeting})

        # Log greeting
        log_message(base_name, user_id, session_id, "bot", greeting)

        # Add FAQs
        faqs = get_top_faqs(base_name)
        if faqs:
            faq_text = "Here are some common questions you can ask:\n" + "\n".join(f"• {q}" for q in faqs)
            messages.append({"type": "bot", "text": faq_text})
            log_message(base_name, user_id, session_id, "bot", faq_text)

        return jsonify({
            'messages': messages,
            'session_id': session_id,
            'greeted': True
        })

    return jsonify({'greeted': False, 'session_id': session_id})

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found in session'}), 400

    data = request.json
    user_input = data.get('message', '')
    session_id = data.get('session_id') or f"sess_{uuid.uuid4().hex[:8]}"
    user_id = session['user_id']
    faiss_path = os.path.join("outputs", base_name, f"{base_name}_index.faiss")
    qa_dataset_path, summary_path = find_qa_and_summary_for_domain(base_name)
    if not qa_dataset_path:
        return jsonify({'response': 'No data found for this domain.'}), 404

    rag = RAGEngine(qa_dataset_path,faiss_path)
    company_context = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
    retrieved_faqs = rag.retrieve_top_k(user_input, k=3)
    context = get_context(base_name, user_id, session_id)
    prompt = f"Company: {company_context}\nFAQs: {retrieved_faqs}\nContext: {context}\nUser: {user_input}"

    # 🔥 Check if session is new and log greeting message
    is_new = create_session_if_missing(base_name, user_id, session_id)
    if is_new:
        greeting_msg = "👋 Hi! I'm your assistant for this website. How may I help you today?"
        log_message(base_name, user_id, session_id, "bot", greeting_msg)

    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        ai_response = model.generate_content(prompt).text.strip()

        log_message(base_name, user_id, session_id, "user", user_input)
        log_message(base_name, user_id, session_id, "bot", ai_response)

        return jsonify({
            'response': ai_response,
            'session_id': session_id,
            'user_id': user_id,
            'greeted': is_new  # optional flag if frontend wants to know
        })
    except Exception as e:
        print("Gemini error:", e)
        return jsonify({'response': 'Gemini error occurred.'})

@app.route('/get_faqs', methods=['POST'])
def get_faqs():
    try:
        data = request.get_json()
        domain = data.get("domain")

        # 🛠 Fallback for localhost or missing domain
        if not domain or domain in ["127.0.0.1", "localhost"]:
            domain = session.get("base_name")

        if not domain:
            return jsonify({"faqs": [], "error": "Missing domain"}), 400

        # ✅ FIXED: Use correct filename
        faq_path = os.path.join("outputs", domain, f"{domain}_qa.json")

        if not os.path.exists(faq_path):
            return jsonify({"faqs": [], "error": f"FAQ file not found: {faq_path}"}), 404

        with open(faq_path, 'r', encoding='utf-8') as f:
            faqs = json.load(f)
            top_faqs = [item['question'] for item in faqs[:3]]
            return jsonify({"faqs": top_faqs})

    except Exception as e:
        print("❌ Error in /get_faqs:", str(e))
        return jsonify({"faqs": [], "error": str(e)}), 500

@app.route('/sessions')
def get_sessions():
    if 'user_id' not in session:
        return jsonify([])
    base_name = session.get('base_name')
    return jsonify(get_all_sessions(base_name, session['user_id']))

@app.route('/session/<session_id>')
def get_session_messages(session_id):
    if 'user_id' not in session:
        return jsonify([])
    base_name = session.get('base_name')
    return jsonify(get_messages_for_session(base_name, session['user_id'], session_id))

@app.route('/session/<session_id>/messages', methods=['GET'])
def session_messages(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    base_name = session.get('base_name')
    user = session['user_id']
    sessions = get_all_sessions(base_name, user)
    session_data = next((s for s in sessions if s['session_id'] == session_id), None)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(session_data.get('messages', []))


# === Run App ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
