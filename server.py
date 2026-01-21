# server.py (updated)
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from urllib.parse import urlparse
from sentence_transformers import SentenceTransformer
import os, uuid, logging
from database.auth import validate_user, register_user
from flask_cors import CORS
from database.mongo_storage import (
    get_summary, get_title, get_chunks,save_chunks_and_index_to_mongo, retrieve_top_k_from_mongo,get_context, log_message, create_session_if_missing,
    get_all_sessions, get_messages_for_session, create_session, delete_all_data, add_custom_chunks, get_data_stats
)
from utilities.crawl_utils import check_existing_data,crawl_site, clean_domain_name
from utilities.faiss_utils import build_faiss_index, split_into_chunks
from utilities.llm_utils import run_gemini
# Load embedding model once at startup
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
embedding_model = SentenceTransformer(EMBED_MODEL)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Enable CORS for widget to work on any hosted website
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/widget.js": {"origins": "*"},
    r"/redirect-widget.js": {"origins": "*"}
}, supports_credentials=True)

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Request logging middleware
@app.before_request
def log_request():
    """Log all incoming requests for testing purposes"""
    logging.info(f"🌐 {request.method} {request.path} - {request.remote_addr}")

@app.after_request
def log_response(response):
    """Log response status"""
    status_emoji = "✅" if response.status_code < 400 else "❌"
    logging.info(f"{status_emoji} {request.method} {request.path} - Status: {response.status_code}")
    return response


# helper to safely build prompt pieces
def make_snippets_text(retrieved_chunks, max_chars=1500): 
    #Convert retrieved_chunks (list of dicts or strings) into a truncated,prompt-safe string. Avoid dumping entire pages into the prompt.
    texts = []
    for c in retrieved_chunks:
        if isinstance(c, dict):
            t = c.get("text", "")
        else:
            t = str(c)
        t = t.strip()
        if not t:
            continue
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
            return render_template("url_input.html",
                                   error="Please provide both website URL and your email.",
                                   bot_name="bot")

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
            if check_existing_data(base_name):
                print(f"✅ Existing FAISS/chunk data found for {base_name}, skipping crawl.")
                return redirect(url_for('login'))

            print(f"🌐 Crawling and generating new data for {base_name}...")
            website_text, website_title = crawl_site(url)
            if not website_text:
                return render_template("url_input.html", error="Website content could not be extracted.", bot_name="bot")
            all_combined = "\n\n".join([website_text])
            if not all_combined.strip():
                return render_template("url_input.html", error="Website yielded no textual content.", bot_name="bot")
            website_title = website_title or url

            chunks = split_into_chunks(all_combined, chunk_size=1000, overlap=200)
            if not chunks:
                return render_template("url_input.html", error="Failed to split website text into chunks.", bot_name="bot")
            normalized_chunks = [
                {"text": str(c), "title": website_title} if not isinstance(c, dict) else c
                for c in chunks            ]
            index_obj, mapping = build_faiss_index(embedding_model, normalized_chunks)
            save_chunks_and_index_to_mongo(base_name, website_title, "", normalized_chunks, index_obj)

            print(f"✅ Data for {base_name} saved successfully!")
            return redirect(url_for('login'))

        except Exception as e:
            logging.exception("❌ Processing error while indexing website")
            return render_template("url_input.html",
                                   error="Failed to process website. Please try again.",
                                   bot_name="bot")
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
        try:
            username = request.form.get("username")
            password = request.form.get("password")
            
            success, msg = (
                register_user(base_name, username, password) if mode == "signup"
                else validate_user(base_name, username, password)
            )
            
            if success:
                session.permanent = True
                session["user_id"] = username
                logging.info(f"✅ User {'registered' if mode == 'signup' else 'logged in'}: {username}")
                return redirect(url_for('homee'))
            
            logging.warning(f"⚠️ Authentication failed for {username}: {msg}")
            return render_template("login.html", error=msg, mode=mode, bot_name=base_name)
        
        except Exception as e:
            logging.exception(f"❌ Unexpected error during {'signup' if mode == 'signup' else 'login'}")
            error_msg = "❌ An unexpected error occurred. Please try again."
            return render_template("login.html", error=error_msg, mode=mode, bot_name=base_name)
    
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

@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Streaming chat endpoint using Server-Sent Events for real-time responses."""
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
        return jsonify({'error': 'Please send a question.'}), 400

    def generate():
        """Generator function for SSE streaming."""
        try:
            # Retrieve context - INCREASED for better accuracy
            retrieved_chunks = retrieve_top_k_from_mongo(base_name, user_input, k=10)
            if not retrieved_chunks:
                yield f"data: {json.dumps({'error': 'No data found'})}\n\n"
                return

            snippets_text = make_snippets_text(retrieved_chunks, max_chars=1500)
            summary_context = get_summary(base_name) or ""
            context = get_context(base_name, user_id, session_id) or ""

            # Session handling
            is_new = create_session_if_missing(base_name, user_id, session_id)
            if is_new:
                create_session(user_id, session_id, base_name)
                greeting_msg = "👋 Hi! I'm your assistant for this website. How may I help you today?"
                log_message(base_name, user_id, session_id, "bot", greeting_msg)

            # Build prompt - STRENGTHENED to prevent hallucinations
            prompt = f"""You are a helpful assistant for {base_name}.

IMPORTANT RULES:
1. Answer ONLY using information from the "Website Content" below
2. If the answer is NOT in the content, say "I don't have that information in my knowledge base"
3. Be specific - mention exact prices, product names, details from the content
4. Do NOT make up or guess information

Website Content:
{snippets_text}

User Question: {user_input}

Answer (based ONLY on the content above):"""

            # Stream LLM response
            full_response = ""
            try:
                gen = run_gemini(prompt)
                for chunk in gen:
                    if chunk is None:
                        continue
                    chunk_str = str(chunk)
                    full_response += chunk_str
                    # Send chunk to frontend
                    yield f"data: {json.dumps({'chunk': chunk_str})}\n\n"
            except Exception as e:
                logging.exception("LLM streaming error")
                yield f"data: {json.dumps({'error': 'Generation failed'})}\n\n"
                return

            # Log messages
            try:
                log_message(base_name, user_id, session_id, "user", user_input)
                log_message(base_name, user_id, session_id, "bot", full_response)
            except Exception:
                logging.exception("Failed to log messages")

            # Send completion signal
            yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

        except Exception as e:
            logging.exception("Chat stream error")
            yield f"data: {json.dumps({'error': 'Processing failed'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

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

        # Build optimized prompt - concise but maintains quality
        prompt = f"""You are AURA, AI assistant for {base_name}.

Context: {summary_context[:300] if summary_context else 'General assistant'}

Relevant info: {snippets_text[:600]}

Recent conversation: {context[:300] if context else 'First message'}

User: {user_input}

Respond in 2-3 helpful sentences. Be professional and friendly."""

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

        prompt = f"""You are AURA, a friendly and professional AI assistant for {domain}.
Context you can use:
- Company Background: {summary_context}
- Relevant Website Snippets: {snippets_text}
- Recent Conversation: {context}

User’s Question: {message}
"""

        # Generate response safely
        try:
            gen = run_gemini(prompt)
            if isinstance(gen, str):
                ai_response = gen
            else:
                ai_response = ""
                for chunk in gen:
                    if chunk is not None:
                        ai_response += str(chunk)
        except Exception:
            logging.exception("Widget LLM generation error")
            ai_response = "❌ Server not responding."

        if not ai_response.strip():
            ai_response = "❌ Server not responding."

        # Log messages
        try:
            log_message(base_name, user_id, session_id, "user", message)
            log_message(base_name, user_id, session_id, "bot", ai_response)
        except Exception:
            logging.exception("Widget message logging error")

        return jsonify({'response': ai_response,'session_id': session_id,'domain': domain
        })

    except Exception:
        logging.exception("Error generating")
        return jsonify({'response': "❌ Server not responding.",'session_id': session_id,'domain': domain})

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

@app.route('/widget.js')
def serve_widget():
    return render_template('widget.js')

@app.route('/redirect-widget.js')
def serve_redirect_widget():
    return render_template('redirect-widget.js')

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
    samples_short = [
    ( (s.get("text", "") if isinstance(s, dict) else str(s))[:200] +
      ("..." if len((s.get("text", "") if isinstance(s, dict) else str(s))) > 200 else "") )
    for s in (get_chunks(base_name) or [])[:5]
    ]
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


@app.route('/settings')
def settings():
    """Settings page for data management"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    base_name = session.get('base_name')
    if not base_name:
        return redirect(url_for('index'))
    
    # Get data statistics
    stats = get_data_stats(base_name)
    user_email = session.get('user_email', '')
    domain = user_email.split('@')[-1] if user_email else 'unknown'
    
    return render_template('settings.html',
                         username=session.get('user_id'),
                         domain=domain,
                         base_name=base_name,
                         stats=stats)


@app.route('/retrain', methods=['POST'])
def retrain():
    """Complete retrain - delete and re-crawl website"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    base_name = session.get('base_name')
    user_email = session.get('user_email')
    
    if not base_name or not user_email:
        return jsonify({'error': 'Missing session data'}), 400
    
    try:
        # Get URL from session or reconstruct
        domain = user_email.split('@')[-1]
        url = f"https://{domain}"
        
        logging.info(f"🔄 Starting retrain for {base_name}")
        
        # Delete existing data
        if not delete_all_data(base_name):
            return jsonify({'error': 'Failed to delete existing data'}), 500
        
        # Re-crawl website
        website_text, website_title = crawl_site(url)
        if not website_text:
            return jsonify({'error': 'Failed to crawl website'}), 500
        
        # Process and index
        chunks = split_into_chunks(website_text, chunk_size=1000, overlap=200)
        if not chunks:
            return jsonify({'error': 'Failed to create chunks'}), 500
        
        normalized_chunks = [
            {"text": str(c), "title": website_title} if not isinstance(c, dict) else c
            for c in chunks
        ]
        
        from utilities.faiss_utils import build_faiss_index
        index_obj, mapping = build_faiss_index(embedding_model, normalized_chunks)
        save_chunks_and_index_to_mongo(base_name, website_title, "", normalized_chunks, index_obj)
        
        logging.info(f"✅ Retrain completed for {base_name}")
        
        return jsonify({
            'success': True,
            'message': 'Data retrained successfully',
            'chunks_count': len(normalized_chunks)
        })
        
    except Exception as e:
        logging.exception(f"❌ Retrain failed for {base_name}")
        return jsonify({'error': f'Retrain failed: {str(e)}'}), 500


@app.route('/add-custom-data', methods=['POST'])
def add_custom_data_route():
    """Add custom FAQs/data to knowledge base"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400
    
    data = request.json or {}
    custom_text = data.get('custom_text', '').strip()
    custom_title = data.get('title', 'Custom Data').strip()
    
    if not custom_text:
        return jsonify({'error': 'Custom text is required'}), 400
    
    # Limit size to 50KB
    if len(custom_text) > 50000:
        return jsonify({'error': 'Custom text too large (max 50KB)'}), 400
    
    try:
        logging.info(f"📝 Adding custom data to {base_name}")
        
        success, count = add_custom_chunks(base_name, custom_text, custom_title)
        
        if not success:
            return jsonify({'error': 'Failed to add custom data'}), 500
        
        logging.info(f"✅ Added {count} custom chunks to {base_name}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully added {count} custom chunks',
            'chunks_added': count
        })
        
    except Exception as e:
        logging.exception(f"❌ Add custom data failed for {base_name}")
        return jsonify({'error': f'Failed to add custom data: {str(e)}'}), 500


@app.route('/data-stats')
def data_stats():
    """Get current data statistics"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    base_name = session.get('base_name')
    if not base_name:
        return jsonify({'error': 'No base_name found'}), 400
    
    try:
        stats = get_data_stats(base_name)
        return jsonify(stats)
    except Exception as e:
        logging.exception("Stats error")
        return jsonify({'error': 'Failed to get stats'}), 500



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), debug=True)