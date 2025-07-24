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
global  base_name
from db_utils import (
    get_context, log_message, create_session_if_missing,
    get_all_sessions, get_messages_for_session,
)
from auth import validate_user, register_user

# === Gemini Configuration ===
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs")

app = Flask(__name__)
app.secret_key = "supersecretkey"
visited = set()

# === Utility Functions ===

def clean_domain_name(url):
    domain = urlparse(url).netloc
    return domain.replace("www.", "").replace(".", "_").strip().lower()

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

def crawl_site(start_url, max_pages=100):
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

    # 👇 Normal crawling flow
    driver = setup_driver()
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
            to_visit.extend(
                link for link in extract_links(driver, url, base_domain)
                if link not in visited and link not in to_visit
            )
        except Exception as e:
            print(f"⚠️ Error visiting {url}: {e}")
            continue

    driver.quit()
    return all_text, extracted_title
def convert_to_qa(text):
    prompt = f'''
You are a domain-agnostic AI assistant specialized in transforming raw text into structured knowledge.

Your task is to read the following input and generate a clean, diverse set of Question-Answer (Q&A) pairs.

Instructions:
- Generate at least 200 meaningful Q&A pairs.
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

# === ROUTES ===

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Please provide a valid URL."
        
        website_text, website_title = crawl_site(url)
        all_combined = "\n\n".join(website_text.values())
        qa_list = convert_to_qa(all_combined)
        summary_context = generate_website_context(all_combined)
        base_name = clean_domain_name(url)
        session['base_name'] = base_name
        folder_path = os.path.join("outputs", base_name)
        os.makedirs(folder_path, exist_ok=True)


        with open(os.path.join(folder_path, f"{base_name}_qa.json"), "w", encoding="utf-8") as f:
            json.dump(qa_list, f, indent=2)
        with open(os.path.join(folder_path, f"{base_name}_summary.txt"), "w", encoding="utf-8") as f:
            f.write(summary_context)
        with open(os.path.join(folder_path, f"{base_name}_title.txt"), "w", encoding="utf-8") as f:
            f.write(website_title)
        
        return redirect(url_for('login'))

    return '''
        <form method="post">
            <label>Website URL:</label>
            <input type="text" name="url" placeholder="https://example.com" required>
            <input type="submit" value="Generate Q&A + Summary + Title">
        </form>
    '''
@app.route('/homee')
def homee():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # If base_name not in session, recover it from available folders
    base_name = session.get('base_name')
    if not base_name:
        # 🔍 Try recovering latest one from outputs/
        existing_folders = os.listdir('outputs')
        if existing_folders:
            base_name = existing_folders[-1]  # use most recent
            session['base_name'] = base_name
        else:
            return "No website data found. Please generate data first."

    qa_dataset_path, summary_path = find_qa_and_summary_for_domain(base_name)

    if summary_path and os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            company_context = f.read().strip()
    else:
        company_context = ""

    rag = RAGEngine(qa_dataset_path) if qa_dataset_path else None

    # 🖥️ Render chatbot UI
    
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
    base_name = session.get("base_name")
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
            return redirect(url_for('homee'))
        else:
            return render_template("login.html", error=msg, mode=mode, bot_name=base_name)
    return render_template("login.html", mode=mode, bot_name=base_name)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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

    qa_dataset_path, summary_path = find_qa_and_summary_for_domain(base_name)
    if not qa_dataset_path:
        return jsonify({'response': 'No data found for this domain.'}), 404

    rag = RAGEngine(qa_dataset_path)
    company_context = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
    retrieved_faqs = rag.retrieve_top_k(user_input, k=3)
    context = get_context(user_id, session_id)
    prompt = f"Company: {company_context}\nFAQs: {retrieved_faqs}\nContext: {context}\nUser: {user_input}"

    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        ai_response = model.generate_content(prompt).text.strip()
        create_session_if_missing(user_id, session_id)
        log_message(user_id, session_id, "user", user_input)
        log_message(user_id, session_id, "bot", ai_response)

        return jsonify({'response': ai_response, 'session_id': session_id, 'user_id': user_id})
    except Exception as e:
        return jsonify({'response': 'Gemini error occurred.'})

@app.route('/sessions')
def get_sessions():
    if 'user_id' not in session:
        return jsonify([])
    return jsonify(get_all_sessions(session['user_id']))

@app.route('/session/<session_id>')
def get_session_messages(session_id):
    if 'user_id' not in session:
        return jsonify([])
    return jsonify(get_messages_for_session(session['user_id'], session_id))

@app.route('/session/<session_id>/messages', methods=['GET'])
def session_messages(session_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = session['user_id']
    sessions = get_all_sessions(user)
    session_data = next((s for s in sessions if s['session_id'] == session_id), None)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(session_data['messages'])

# === Run App ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
