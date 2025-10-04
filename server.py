# server.py (updated)
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from urllib.parse import urlparse
from sentence_transformers import SentenceTransformer
import os, uuid, logging
from database.auth import validate_user, register_user
from flask_cors import CORS

from database.mongo_storage import (
    get_summary, get_title, get_chunks,
    save_chunks_and_index_to_mongo, retrieve_top_k_from_mongo
)
from database.db_utils import (
    get_context, log_message, create_session_if_missing,
    get_all_sessions, get_messages_for_session, create_session
)
from utilities.crawl_utils import crawl_site, clean_domain_name
from utilities.faiss_utils import build_faiss_index, split_into_chunks
from utilities.llm_utils import run_gemini, generate_website_context
# Load embedding model once at startup
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
embedding_model = SentenceTransformer(EMBED_MODEL)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")
CORS(app, origins=['*'])

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# helper to safely build prompt pieces
def make_snippets_text(retrieved_chunks, max_chars=1500):
    """
    Convert retrieved_chunks (list of dicts or strings) into a truncated,
    prompt-safe string. Avoid dumping entire pages into the prompt.
    """
    texts = []
    for c in retrieved_chunks:
        if isinstance(c, dict):
            t = c.get("text", "")
        else:
            t = str(c)
        t = t.strip()
        if not t:
            continue
        # take first ~600 chars of each snippet to avoid huge prompts
        snippet = t[:600]
        texts.append(snippet + ("..." if len(t) > 600 else ""))
        if sum(len(s) for s in texts) > max_chars:
            break
    return "\n\n".join(texts)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        email = request.form.get("email")
        if not url or not email:
            return render_template("url_input.html", error="Please provide both website URL and your email.", bot_name="bot")

        parsed = urlparse(url)
        domain = (parsed.hostname or "").replace("www.", "").lower()
        email_domain = email.split('@')[-1].lower()
        if email_domain != domain:
            return render_template("url_input.html",
                                   error=f"Email domain ({email_domain}) must match website domain ({domain}).",
                                   bot_name="bot")

        base_name = clean_domain_name(url)
        session['base_name'] = base_name
        session['user_email'] = email

        try:
            existing_summary = get_summary(base_name)
            existing_title = get_title(base_name)
            if existing_summary and existing_title:
                return redirect(url_for('login'))

            website_text, website_title = crawl_site(url)
            if not website_text:
                return render_template("url_input.html", error="Website content could not be extracted.", bot_name="bot")
# normalize: put everything in a single chunk
            texts_only = [website_text]

            all_combined = "\n\n".join([t for t in texts_only if t.strip()])
            if not all_combined.strip():
                return render_template("url_input.html", error="Website yielded no textual content.", bot_name="bot")
            # Summarize (index-level summary)
            summary_context = generate_website_context(all_combined)
            website_title = website_title or (get_title(base_name) or url)
            # Split into chunks
            chunks = split_into_chunks(all_combined, chunk_size=1000, overlap=200)
            if not chunks:
                return render_template("url_input.html", error="Failed to split website text into chunks.", bot_name="bot")

# Normalize chunks into dicts (ensures FAISS + Mongo can handle them consistently)
            normalized_chunks = []
            for c in chunks:
                if isinstance(c, dict):
                    normalized_chunks.append(c)
                else:
                    normalized_chunks.append({
                        "text": str(c),
                        "title": website_title or ""
                    }
                )
# Extract texts for FAISS embeddings
            texts_only = [nc["text"] for nc in normalized_chunks]
# normalized_chunks = [{"text": "...", "title": "..."}, ...]
            index_obj, mapping = build_faiss_index(embedding_model, normalized_chunks)

# Save normalized chunks + serialized index to mongo
            save_chunks_and_index_to_mongo(base_name, website_title, summary_context, normalized_chunks, index_obj)
            return redirect(url_for('login'))

        except Exception as e:
            logging.exception("❌ Processing error while indexing website")
            return render_template("url_input.html", error="Failed to process website. Please try again.", bot_name="bot")

    return render_template("url_input.html", bot_name="bot")


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
        snippet_count = len(get_chunks(base_name) or [])
        rag_available = snippet_count > 0
    except Exception as e:
        logging.exception("RAG load error")
        rag_available = False
        snippet_count = 0

    widget_ready = bool(company_context and snippet_count > 0)
    sessions = get_all_sessions(base_name, session.get('user_id'))
    return render_template(
        "index.html",
        username=session.get('user_id'),
        company_context=company_context,
        rag_available=rag_available,
        bot_name=base_name,
        domain=domain,
        faq_count=snippet_count,
        widget_ready=widget_ready,
        sessions=sessions
    )


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
        logging.exception("Sessions error")
        return jsonify({'error': 'Failed to fetch sessions'}), 500


@app.route("/session/<session_id>", methods=["GET"])
def fetch_session(session_id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    base_name = session.get("base_name")
    username = session.get("user_id")
    if not base_name or not username:
        return jsonify({"error": "Missing session context"}), 400

    messages = get_messages_for_session(base_name, username, session_id)
    if not messages:
        return jsonify({"error": "Session not found or no messages"}), 404

    return jsonify({"session_id": session_id, "messages": messages})


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
            samples = (get_chunks(base_name) or [])[:3]
            sample_texts = [
                (s.get("text", "")[:240] + ("..." if len(s.get("text", "")) > 240 else ""))
                for s in samples
            ]

            return jsonify({'messages': messages, 'session_id': session_id, 'greeted': True, 'samples': sample_texts})
        return jsonify({'greeted': False, 'session_id': session_id})
    except Exception as e:
        logging.exception("Greet error")
        return jsonify({'error': 'Failed to process greeting'}), 500

from flask import Response

from flask import Response, jsonify

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400

    data = request.json or {}
    user_input = (data.get('message') or "").strip()
    session_id = data.get('session_id') or f"sess_{uuid.uuid4().hex[:8]}"
    user_id = session['user_id']

    if not user_input:
        return jsonify({'response': 'Please send a question.'}), 400

    try:
        # Retrieve top-k chunks from FAISS
        retrieved_chunks = retrieve_top_k_from_mongo(base_name, user_input, k=4)
        if not retrieved_chunks:
            return jsonify({'response': 'No data found for this domain.'}), 404

        snippets_text = make_snippets_text(retrieved_chunks, max_chars=1200)
        summary_context = get_summary(base_name) or ""
        context = get_context(base_name, user_id, session_id) or ""

        # Session creation + greeting handling (log greeting if new)
        is_new = create_session_if_missing(base_name, user_id, session_id)
        if is_new:
            create_session(user_id, session_id, base_name)
            greeting_msg = "👋 Hi! I'm your assistant for this website. How may I help you today?"
            log_message(base_name, user_id, session_id, "bot", greeting_msg)

        # Build compact prompt
        prompt = f"""
You are Inara, a professional AI assistant for {base_name}.
Use this context:
- Company Info: {summary_context}
- Website Snippets: {snippets_text}
- Recent Chat: {context}
User Question: {user_input}
Instructions:
- Answer in 2-3 short sentences.
- Use company info if relevant.
- Ask for clarification if unsure.
- End by asking if user needs more help.
"""

        # Generate a full response (support both streaming generator or plain string)
        partial_response = ""
        try:
            gen = run_gemini(prompt)
            # If run_gemini returned a string (non-iterable text)
            if isinstance(gen, str):
                partial_response = gen
            else:
                # If it's an iterator/generator that yields chunks
                for chunk in gen:
                    if chunk is None:
                        continue
                    partial_response += str(chunk)
        except Exception as e:
            logging.exception("LLM generation error")
            # graceful fallback message
            partial_response = "❌ Server not responding."

        # Ensure we always have something to return
        if not partial_response or not str(partial_response).strip():
            partial_response = "❌ Server not responding."

        # Log messages (user + bot)
        try:
            log_message(base_name, user_id, session_id, "user", user_input)
            log_message(base_name, user_id, session_id, "bot", partial_response)
        except Exception:
            logging.exception("Failed to log chat messages")

        # Return JSON (front-end expects JSON)
        return jsonify({'response': partial_response, 'session_id': session_id})

    except Exception as e:
        logging.exception("Chat error")
        return jsonify({'response': 'An error occurred while processing your request.'}), 500


@app.route('/get_chunks', methods=['POST'])
def get_chunks_route():
    base_name = session.get('base_name')
    if not base_name:
        return jsonify({"chunks": [], "error": "No base_name found"}), 400
    try:
        sample_chunks = (get_chunks(base_name) or [])[:3]
        sample_snips = [
            (c.get("text", "")[:300] + ("..." if len(c.get("text", "")) > 300 else ""))
            for c in sample_chunks
        ]
        return jsonify({"chunks": sample_snips})
    except Exception as e:
        logging.exception("Chunks error")
        return jsonify({"chunks": [], "error": str(e)}), 500


@app.route('/widget/<domain>')
def widget_interface(domain):
    base_name = clean_domain_name(f"https://{domain}")
    if not get_summary(base_name):
        return jsonify({'error': 'Chatbot not found for this domain'}), 404
    title = get_title(base_name) or domain
    summary = get_summary(base_name) or f"Chat with {domain}"
    return render_template('widget.html', domain=domain, base_name=base_name, title=title, summary=summary)


@app.route('/api/widget/chat', methods=['POST'])
def widget_chat():
    data = request.json or {}
    domain = data.get('domain')
    message = data.get('message')
    session_id = data.get('session_id') or f"widget_{uuid.uuid4().hex[:8]}"
    if not domain or not message:
        return jsonify({'error': 'Domain and message required'}), 400

    base_name = clean_domain_name(f"https://{domain}")
    try:
        retrieved_chunks = retrieve_top_k_from_mongo(base_name, message, k=4)
        if not retrieved_chunks:
            return jsonify({'error': 'Chatbot not found for this domain'}), 404

        snippets_text = make_snippets_text(retrieved_chunks, max_chars=1000)
        summary_context = get_summary(base_name) or ""
        user_id = f"widget_user_{session_id}"
        context = get_context(base_name, user_id, session_id, limit=3) or ""

        prompt = f"""You are Inara, a friendly and professional AI assistant for {domain}.
Context you can use:
- Company Background: {summary_context}
- Relevant Website Snippets: {snippets_text}
- Recent Conversation: {context}

User’s Question: {message}
"""
        ai_response = run_gemini(prompt)

        log_message(base_name, user_id, session_id, "user", message)
        log_message(base_name, user_id, session_id, "bot", ai_response)
        return jsonify({'response': ai_response, 'session_id': session_id, 'domain': domain})
    except Exception as e:
        logging.exception("Widget chat error")
        return jsonify({'error': 'Failed to process message'}), 500


@app.route('/api/widget/greet', methods=['POST'])
def widget_greet():
    data = request.json or {}
    domain = data.get('domain')
    if not domain:
        return jsonify({'error': 'Domain required'}), 400
    base_name = clean_domain_name(f"https://{domain}")
    try:
        title = get_title(base_name) or domain
        samples = (get_chunks(base_name) or [])[:3]
        sample_texts = [
                (s.get("text", "")[:240] + ("..." if len(s.get("text", "")) > 240 else ""))
                for s in samples
            ]
        greeting = f"👋 Hi! I'm the assistant for {title}. How can I help you today?"
        return jsonify({'greeting': greeting, 'samples': sample_texts, 'title': title, 'session_id': f"widget_{uuid.uuid4().hex[:8]}"})
    except Exception as e:
        logging.exception("Widget greet error")
        return jsonify({'error': 'Failed to get greeting'}), 500


@app.route('/generate-embed-code/<domain>')
def generate_embed_code(domain):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
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
    """
    return jsonify({'embed_code': embed_code.strip(), 'domain': domain, 'instructions': ['Copy the code above','Paste before </body>','Widget will appear on site']})

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
        logging.exception("Session messages error")
        return jsonify({'error': 'Failed to fetch session messages'}), 500


@app.route('/widget-demo')
def widget_demo():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    base_name = session.get('base_name')
    user_email = session.get('user_email')
    if not base_name or not user_email:
        return redirect(url_for('index'))
    domain = user_email.split('@')[-1]
    title = get_title(base_name) or domain
    summary = get_summary(base_name) or f"Chatbot for {domain}"
    samples_short = [(s[:200] + ("..." if len(s) > 200 else "")) for s in (get_chunks(base_name) or [])[:5]]
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
'''
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
'''
    return render_template('widget_demo.html',
                           domain=domain,
                           title=title,
                           summary=summary,
                           faqs=samples_short,
                           chat_embed_code=chat_embed_code,
                           redirect_embed_code=redirect_embed_code,
                           api_base=request.host_url)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), debug=True)
