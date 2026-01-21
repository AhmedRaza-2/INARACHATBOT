import requests, json, logging, shutil, subprocess, time, os

def run_gemini(prompt: str):
    """
    ⚡ Fast AI responses using free cloud APIs with local fallback.
    Priority: Groq (0.5-2s) > Gemini (1-3s) > Ollama (slow but offline)
    """
    # Try Groq API first (fastest and free!)
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            return _run_groq_api(prompt, groq_api_key)
        except Exception as e:
            logging.warning(f"Groq API failed: {e}")
    
    # Try Google Gemini API (fast and free)
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key:
        try:
            return _run_gemini_api(prompt, gemini_api_key)
        except Exception as e:
            logging.warning(f"Gemini API failed: {e}")
    
    # Fallback to local Ollama (slower but works offline)
    logging.info("No API keys found, using local Ollama (slower)")
    return _run_ollama(prompt)


def _run_groq_api(prompt: str, api_key: str):
    """Use Groq API for ultra-fast responses (0.5-2 seconds). FREE tier available!"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "llama-3.1-8b-instant",  # Fast and high quality
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,  # More focused responses
        "max_tokens": 300,  # Increased to prevent cutoff
        "top_p": 0.9,
    }
    
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    
    elapsed = round(time.time() - start, 1)
    logging.info(f"✅ Groq API responded in {elapsed}s (model: llama-3.1-8b-instant)")
    
    yield text


def _run_gemini_api(prompt: str, api_key: str):
    """Use Google Gemini API for fast responses (1-3 seconds)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.6,  # More focused responses
            "topP": 0.9,
            "topK": 40,
            "maxOutputTokens": 300,  # Increased to prevent cutoff
        }
    }
    
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    
    elapsed = round(time.time() - start, 1)
    logging.info(f"✅ Gemini API responded in {elapsed}s (model: gemini-1.5-flash)")
    
    yield text


def _run_ollama(prompt: str):
    """Fallback to local Ollama (slower but works offline)."""
    has_gpu = shutil.which("nvidia-smi") is not None
    model = "gemma2:2b"
    
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=3)
        if "gemma2:2b" not in result.stdout.lower():
            if "gemma2" in result.stdout.lower():
                model = "gemma2"
            else:
                model = "gemma2:2b"
    except Exception:
        model = "gemma2:2b"

    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": model,
        "prompt": prompt.strip(),
        "stream": True,
        "keep_alive": "6h",
        "options": {
            "temperature": 0.7,
            "num_predict": 80,
            "top_p": 0.9,
            "num_ctx": 1024,
            "num_thread": 16,
            "num_batch": 512,
            "repeat_penalty": 1.15,
            "top_k": 40,
        },
    }

    start = time.time()
    try:
        with requests.post(url, headers=headers, data=json.dumps(payload),
                           stream=True, timeout=(5, 90)) as response:
            response.raise_for_status()
            got_data = False
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "response" in data:
                        got_data = True
                        yield data["response"]
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

            if not got_data:
                yield "⚠️ No response chunks received — model may be initializing."

    except requests.exceptions.ReadTimeout:
        logging.error(f"⚠️ Ollama ({model}) timed out after 90 sec.")
        yield "⚠️ Model took too long to respond. Please try again."
    except requests.exceptions.ConnectionError:
        logging.error("❌ Ollama server not reachable.")
        yield "❌ Ollama server not reachable. Make sure it's running: `ollama serve`"
    except Exception as e:
        logging.exception(f"❌ Ollama ({model}) generation error: %s", e)
        yield f"❌ Error generating response. Please try again."

    elapsed = round(time.time() - start, 1)
    logging.info(f"✅ Ollama responded in {elapsed}s (model: {model}, GPU: {has_gpu})")

