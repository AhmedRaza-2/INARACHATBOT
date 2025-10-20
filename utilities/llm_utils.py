import requests,json,logging,shutil,subprocess,time
def run_gemini(prompt: str):
    """
    ⚡ Ultra-fast Ollama version — optimized for instant response.
    Uses Gemma2 or Mistral, keeps model hot, and minimizes token generation delay.
    """
    # 🔍 Detect GPU automatically
    has_gpu = shutil.which("nvidia-smi") is not None

    # 🧠 Pick smallest fast model available
    model = "gemma2:2b"
    try:
        subprocess.run(["ollama", "show", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        model = "mistral:7b"  # fast alternative if gemma2 missing

    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": model,
        "prompt": prompt.strip(),
        "stream": True,
        "keep_alive": "4h",  # ✅ stay warm
        "options": {
            "temperature": 0.5,
            "num_predict": 64,  # ✅ generate fewer tokens for faster start
            "top_p": 0.8,
            "num_ctx": 512,     # ✅ smaller context = faster
            "use_gpu": has_gpu,
            "num_thread": 8,    # ✅ parallelize CPU if no GPU
        },
    }

    start = time.time()
    try:
        with requests.post(url, headers=headers, data=json.dumps(payload),
                           stream=True, timeout=(10, 60)) as response:
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
        logging.error("⚠️ Ollama timed out after 60 sec.")
        yield "⚠️ Model took too long to respond (try again — may be cold start)."
    except requests.exceptions.ConnectionError:
        yield "❌ Ollama server not reachable. Try running: `ollama serve`."
    except Exception as e:
        logging.exception("❌ Ollama generation error: %s", e)
        yield f"❌ Local LLM error: {e}"

    elapsed = round(time.time() - start, 1)
    logging.info(f"✅ Ollama responded in {elapsed}s (model: {model}, GPU: {has_gpu})")
