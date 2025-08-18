from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
import faiss,numpy as np
import os, time, json, re, uuid
import google.generativeai as genai
from Auth.auth import validate_user, register_user
from Auth.Rag.rag import RAGEngine
from flask_cors import CORS
from DataBase.mongo_storage import (
    get_faqs as mongo_get_faqs, 
    save_chatbot_data, 
    get_summary, 
    get_title, 
    store_summary, 
    store_title, 
    store_faqs
)
from DataBase.db_utils import (
    get_context, 
    log_message, 
    create_session_if_missing,
    get_all_sessions, 
    get_messages_for_session,
    create_session
)

genai.configure(api_key="AIzaSyAtJoxVJxwbkW1qpyCNOC4Ld38F1Zzi65E")

app = Flask(__name__)
app.secret_key = "supersecretkey"
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
    
    # CHECK MONGODB INSTEAD OF LOCAL FILES
    print(f"🔍 Checking if data exists in MongoDB for {base_name}...")
    
    try:
        # Check if data already exists in MongoDB
        existing_faqs = mongo_get_faqs(base_name)
        existing_summary = get_summary(base_name)
        existing_title = get_title(base_name)
        
        if existing_faqs and existing_summary and existing_title:
            print(f"✅ Skipping crawl: data already exists in MongoDB for {start_url}")
            print(f"   - Found {len(existing_faqs)} FAQs")
            print(f"   - Found summary: {len(existing_summary)} chars")
            print(f"   - Found title: {existing_title}")
            
            # Return existing data in the expected format
            combined_text = "\n\n".join([item["answer"] for item in existing_faqs])
            return {start_url: combined_text}, existing_title
        else:
            print(f"📄 No complete data found in MongoDB for {base_name}")
            print(f"   - FAQs: {len(existing_faqs) if existing_faqs else 0}")
            print(f"   - Summary: {'Yes' if existing_summary else 'No'}")
            print(f"   - Title: {'Yes' if existing_title else 'No'}")
            print(f"🕷️ Starting fresh crawl...")
            
    except Exception as e:
        print(f"⚠️ Error checking MongoDB, proceeding with crawl: {e}")
    driver = setup_driver()
    to_visit, all_text = [start_url], {}
    extracted_title = ""
    try:
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            print(f"🕷️ Crawling: {url}")
            driver.get(url)
            time.sleep(2)
            
            if not extracted_title:
                extracted_title = extract_title(driver)

            text = extract_visible_text(driver)
            all_text[url] = text
            visited.add(url)
            
            new_links = extract_links(driver, url, base_domain)
            to_visit.extend(link for link in new_links
                          if link not in visited and link not in to_visit)
                          
            print(f"   📄 Extracted {len(text)} chars, found {len(new_links)} new links")
            print(f"   📊 Progress: {len(visited)}/{max_pages} pages crawled")
            
    except Exception as e:
        print(f"❌ Crawling error: {e}")
    finally:
        driver.quit()

    print(f"✅ Crawling completed: {len(all_text)} pages processed")
    return all_text, extracted_title

def convert_to_qa(text):
    prompt = f'''
    Convert the following website content into at least 300 question-answer pairs.
You are a domain-agnostic AI assistant specialized in transforming raw text into structured knowledge.
Your task is to read the following input and generate a clean, diverse set of Question-Answer (Q&A) pairs.

    Instructions:
- Generate at least 300 meaningful Q&A pairs.
again minimum 300 pairs. strictly minimum 300 pairs.
- Cover all important points, facts, sections, or ideas in the text, including numbers.
- Rephrase questions naturally.
- Avoid vague or repetitive questions.
no less than 300 pairs.
300 pairs is the minimum requirement.

Return a JSON array only, like:
plz only this format no other format accpeted 
format it as json array below
[
  {{"question": "What is...", "answer": "..." }},
  ...
]
Do NOT include explanations or summaries. Just return the JSON array. No markdown, no extra text.

Don't return summaries or explanations.
Only return raw JSON. No markdown or additional text.

Text:
"""{text}"""
'''
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
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
        model = genai.GenerativeModel("models/gemini-2.0-flash")
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

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        email = request.form.get("email")

        if not url or not email:
            return render_template("url_input.html", error="Please provide both website URL and your email.", bot_name="bot")

        parsed_url = urlparse(url)
        domain = parsed_url.hostname.replace("www.", "").lower()
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
            print(f"🔄 Processing website: {url}")
            
            print(f"🔍 Quick MongoDB check for {base_name}...")
            existing_faqs = mongo_get_faqs(base_name)
            existing_summary = get_summary(base_name)
            existing_title = get_title(base_name)
            
            if existing_faqs and existing_summary and existing_title:
                print(f"⚡ FAST PATH: Complete data exists in MongoDB!")
                print(f"   📊 Found {len(existing_faqs)} FAQs")
                print(f"   📄 Found summary: {len(existing_summary)} chars")
                print(f"   🏷️ Found title: {existing_title}")
                print(f"⏭️ Skipping all processing, redirecting to login...")
                
                return redirect(url_for('login'))
            
            print(f"📄 Incomplete data in MongoDB, processing required...")
            print(f"   📊 FAQs: {len(existing_faqs) if existing_faqs else 0}")
            print(f"   📄 Summary: {'Yes' if existing_summary else 'No'}")
            print(f"   🏷️ Title: {'Yes' if existing_title else 'No'}")
            
            website_text, website_title = crawl_site(url)
            
            if not website_text:
                print("❌ No text extracted from website.")
                return render_template("url_input.html", error="Website content could not be extracted.", bot_name="bot")

            updated_faqs = mongo_get_faqs(base_name)
            
            if updated_faqs:
                print("✅ Data now exists in MongoDB (from crawl_site cache), skipping processing")
                return redirect(url_for('login'))
            
            print("🔄 Processing new website data...")
            
            all_combined = "\n\n".join(website_text.values())
            print(f"📄 Combined text length: {len(all_combined)} chars")
            
            print("🤖 Generating Q&A pairs with Ollama...")
            qa_list = convert_to_qa(all_combined)
            print(f"❓ Generated {len(qa_list)} Q&A pairs")
            
            if not qa_list:
                return render_template("url_input.html", error="Failed to generate Q&A pairs from website content.", bot_name="bot")

            # Generate summary
            print("📋 Generating summary with Ollama...")
            summary_context = generate_website_context(all_combined)
            print(f"📋 Generated summary: {len(summary_context)} chars")

            # Create embeddings and FAISS index (expensive!)
            print("🔍 Creating embeddings and FAISS index...")
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode([item["question"] for item in qa_list], show_progress_bar=False)
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(np.array(embeddings))
            print("✅ Embeddings and FAISS index created")

            # Save to MongoDB
            print("💾 Saving data to MongoDB...")
            save_chatbot_data(base_name, website_title, summary_context, qa_list, index)
            print("✅ Data saved successfully")

            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"❌ Processing error: {e}")
            import traceback
            traceback.print_exc()
            return render_template("url_input.html", error="Failed to process website. Please try again.", bot_name="bot")

    return render_template("url_input.html", bot_name="bot")

# Update your existing /homee route to include widget demo link

@app.route('/homee')
def homee():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    base_name = session.get('base_name')
    if not base_name:
        return render_template("index.html", error="No website data found.", bot_name="bot")

    company_context = get_summary(base_name)
    user_email = session.get('user_email', '')
    domain = user_email.split('@')[-1] if user_email else 'unknown'
    
    try:
        rag = RAGEngine(base_name)
        rag_available = True
        faq_count = len(rag.questions)
    except:
        rag_available = False
        faq_count = 0

    # Check if widget is ready
    widget_ready = bool(company_context and faq_count > 0)

    return render_template(
        "index.html",
        username=session['user_id'],
        company_context=company_context,
        rag_available=rag_available,
        bot_name=base_name,
        domain=domain,
        faq_count=faq_count,
        widget_ready=widget_ready
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

        # 🔄 Gemini replaces Ollama here
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
    

# Add CORS support for widget embedding
CORS(app, origins=['*'])  # Allow embedding from any domain

@app.route('/widget.js')
def widget_js():
    """Serve the JavaScript widget code"""
    return render_template('widget.js', mimetype='application/javascript')

@app.route('/widget/<domain>')
def widget_interface(domain):
    """Serve the widget HTML interface"""
    # Validate domain exists in your system
    base_name = clean_domain_name(f"https://{domain}")
    
    # Check if chatbot data exists for this domain
    faqs = mongo_get_faqs(base_name)
    if not faqs:
        return jsonify({'error': 'Chatbot not found for this domain'}), 404
    
    # Get chatbot info
    title = get_title(base_name) or domain
    summary = get_summary(base_name) or f"Chat with {domain}"
    
    return render_template('widget.html', 
                         domain=domain,
                         base_name=base_name,
                         title=title,
                         summary=summary)

@app.route('/api/widget/chat', methods=['POST'])
def widget_chat():
    """Public API endpoint for widget chat"""
    data = request.json
    domain = data.get('domain')
    message = data.get('message')
    session_id = data.get('session_id') or f"widget_{uuid.uuid4().hex[:8]}"
    
    if not domain or not message:
        return jsonify({'error': 'Domain and message required'}), 400
    
    # Convert domain to base_name format
    base_name = clean_domain_name(f"https://{domain}")
    
    # Check if chatbot exists
    try:
        rag = RAGEngine(base_name)
        if not rag.questions:
            return jsonify({'error': 'Chatbot not found for this domain'}), 404
    except:
        return jsonify({'error': 'Chatbot not found for this domain'}), 404
    
    try:
        # Retrieve FAQs and context
        retrieved_faqs = rag.retrieve_top_k(message, k=3)
        summary_context = get_summary(base_name) or ""
        
        # Use anonymous user for widget sessions
        user_id = f"widget_user_{session_id}"
        context = get_context(base_name, user_id, session_id, limit=3)
        
        # Construct prompt
        prompt = f"""You are a helpful assistant for {domain}.
Company Context: {summary_context}
Relevant FAQs: {retrieved_faqs}
Recent Context: {context}
User Question: {message}

Please provide a helpful and accurate response based on the information about {domain}."""

        # 🔄 Gemini replaces Ollama here
        model = genai.GenerativeModel("gemini-2.0-flash")
        ai_response = model.generate_content(prompt).text.strip()
        
        # Log the conversation
        log_message(base_name, user_id, session_id, "user", message)
        log_message(base_name, user_id, session_id, "bot", ai_response)
        
        return jsonify({
            'response': ai_response,
            'session_id': session_id,
            'domain': domain
        })
        
    except Exception as e:
        print(f"Widget chat error: {e}")
        return jsonify({'error': 'Failed to process message'}), 500
@app.route('/redirect-widget.js')
def redirect_widget_js():
    """Serve the redirect widget JavaScript code"""
    return render_template('redirect-widget.js', mimetype='application/javascript')

@app.route('/api/widget/greet', methods=['POST'])
def widget_greet():
    """Get greeting and FAQs for widget"""
    data = request.json
    domain = data.get('domain')
    
    if not domain:
        return jsonify({'error': 'Domain required'}), 400
    
    base_name = clean_domain_name(f"https://{domain}")
    
    try:
        # Get basic info
        title = get_title(base_name) or domain
        faqs = get_top_faqs(base_name, limit=3)
        
        greeting = f"👋 Hi! I'm the assistant for {title}. How can I help you today?"
        
        return jsonify({
            'greeting': greeting,
            'faqs': faqs,
            'title': title,
            'session_id': f"widget_{uuid.uuid4().hex[:8]}"
        })
        
    except Exception as e:
        print(f"Widget greet error: {e}")
        return jsonify({'error': 'Failed to get greeting'}), 500

@app.route('/generate-embed-code/<domain>')
def generate_embed_code(domain):
    """Generate embed code for users"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Verify this domain belongs to the logged-in user
    base_name = session.get('base_name')
    if base_name != clean_domain_name(f"https://{domain}"):
        return jsonify({'error': 'Unauthorized for this domain'}), 403
    
    embed_code = f"""
    <!-- {domain.upper()} Chatbot Widget -->
    <script>
    (function() {{
        var script = document.createElement('script');
        script.src = '{request.host_url}widget.js';
        script.setAttribute('data-domain', '{domain}');
        script.setAttribute('data-position', 'bottom-right');
        script.setAttribute('data-color', '#007bff');
        document.head.appendChild(script);
    }})();
    </script>
    <!-- End {domain.upper()} Chatbot Widget -->
    """
    
    return jsonify({
        'embed_code': embed_code.strip(),
        'domain': domain,
        'instructions': [
            'Copy the code above',
            'Paste it before the closing </body> tag on your website',
            'The chatbot will appear as a floating button on your site',
            'Customize colors and position by editing the data attributes'
        ]
    })

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
    
# Add this route to show users how their widget looks and get embed code

@app.route('/widget-demo')
def widget_demo():
    """Show users their widget demo and embed code"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    base_name = session.get('base_name')
    user_email = session.get('user_email')
    
    if not base_name or not user_email:
        return redirect(url_for('index'))
    
    # Extract domain from email
    domain = user_email.split('@')[-1]
    
    # Get chatbot info
    title = get_title(base_name) or domain
    summary = get_summary(base_name) or f"Chatbot for {domain}"
    faqs = get_top_faqs(base_name, limit=5)
    
    # Generate FULL CHAT embed code (existing)
    chat_embed_code = f'''<!-- {domain.upper()} Chatbot Widget -->
<script>
  (function() {{
    var script = document.createElement('script');
    script.src = '{request.host_url}widget.js';
    script.setAttribute('data-domain', '{domain}');
    script.setAttribute('data-position', 'bottom-right');
    script.setAttribute('data-color', '#007bff');
    document.head.appendChild(script);
  }})();
</script>
<!-- End {domain.upper()} Chatbot Widget -->'''
    
    # Generate REDIRECT embed code (new)
    redirect_embed_code = f'''<!-- {domain.upper()} Support Portal Widget -->
<script>
  (function() {{
    var script = document.createElement('script');
    script.src = '{request.host_url}redirect-widget.js';
    script.setAttribute('data-domain', '{domain}');
    script.setAttribute('data-redirect-url', '{request.host_url}login?base_name={base_name}');
    script.setAttribute('data-position', 'bottom-left');
    script.setAttribute('data-color', '#28a745');
    script.setAttribute('data-text', 'Support Portal');
    document.head.appendChild(script);
  }})();
</script>
<!-- End {domain.upper()} Support Portal Widget -->'''
    
    return render_template('widget_demo.html',
                         domain=domain,
                         title=title,
                         summary=summary,
                         faqs=faqs,
                         chat_embed_code=chat_embed_code,
                         redirect_embed_code=redirect_embed_code,
                         api_base=request.host_url)

# === Run App ===
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
