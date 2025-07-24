from flask import Flask, request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
import os
import json
import re
import requests

from server import find_qa_and_summary_for_domain
from ollama import Client

# === SETUP OLLAMA ===
ollama_client = Client(host='http://localhost:11434')
ollama_model = "mistral"  # Change to llama3 or other if needed

app = Flask(__name__)
visited = set()

# === Clean domain name for folder ===
def clean_domain_name(url):
    domain = urlparse(url).netloc
    domain = re.sub(r'\s+', '', domain)
    domain = domain.replace("www.", "").replace(".", "_").lower()
    return domain

# === Setup Selenium driver ===
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    return webdriver.Chrome(options=chrome_options)

# === Check if URL is valid and belongs to base domain ===
def is_valid(url, base_domain):
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and base_domain in parsed.netloc

# === Extract all internal links from a page ===
def extract_links(driver, base_url, base_domain):
    soup = BeautifulSoup(driver.page_source, "html.parser")
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = urljoin(base_url, a_tag["href"])
        href = href.split("#")[0].rstrip("/")
        if is_valid(href, base_domain):
            links.add(href)
    return links

# === Get visible body text of the page ===
def extract_visible_text(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        return body.text
    except:
        return ""

# === Extract website <title> ===
def extract_title(driver):
    try:
        title_element = driver.find_element(By.TAG_NAME, "title")
        return title_element.get_attribute("innerText").replace("-", " ").strip()
    except:
        return "No title found"

# === Crawl entire site up to `max_pages` ===
def crawl_site(start_url, max_pages=30):
    driver = setup_driver()
    base_domain = urlparse(start_url).netloc
    to_visit = [start_url]
    all_text = {}
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

            links = extract_links(driver, url, base_domain)
            to_visit.extend(link for link in links if link not in visited and link not in to_visit)

        except Exception as e:
            print(f"[-] Failed to load {url}: {e}")
            continue

    driver.quit()
    return all_text, extracted_title

# === Generate Q&A pairs using Ollama ===
def convert_to_qa(text):
    prompt = f"""
You are a helpful assistant. Read the input text below and generate at least 50 meaningful question-answer (Q&A) pairs.

Format:
[
  {{ "question": "...", "answer": "..." }},
  ...
]

Text:
\"\"\"{text}\"\"\"
"""
    try:
        response = ollama_client.chat(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response['message']['content']

        # Cleanup for JSON
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]

        return json.loads(raw)

    except Exception as e:
        print("Ollama QA generation error:", e)
        return []

# === Generate website summary using Ollama ===
def generate_website_context(text):
    prompt = f"""
Summarize the following website content in 3–5 short sentences. Include its offerings, target audience, services, and anything unique.

Text:
\"\"\"{text[:8000]}\"\"\"
"""
    try:
        response = ollama_client.chat(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content'].strip()
    except Exception as e:
        print("Ollama summary error:", e)
        return "No summary available."

# === Main route ===
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Please provide a valid URL."

        website_text, website_title = crawl_site(url)
        combined_text = "\n\n".join(website_text.values())

        qa_list = convert_to_qa(combined_text)
        summary_context = generate_website_context(combined_text)

        base_name = clean_domain_name(url)
        folder_path = os.path.join("outputs", base_name)
        os.makedirs(folder_path, exist_ok=True)

        find_qa_and_summary_for_domain(base_name)

        qa_path = os.path.join(folder_path, f"{base_name}_qa.json")
        context_path = os.path.join(folder_path, f"{base_name}_summary.txt")
        title_path = os.path.join(folder_path, f"{base_name}_title.txt")

        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(qa_list, f, indent=2, ensure_ascii=False)
        with open(context_path, "w", encoding="utf-8") as f:
            f.write(summary_context)
        with open(title_path, "w", encoding="utf-8") as f:
            f.write(website_title)

        # Optional: send to chatbot
        try:
            chat_url = "http://localhost:5001/chat"
            payload = {
                "message": "Hello, what does this company do?",
                "domain": base_name
            }
            response = requests.post(chat_url, json=payload)
            print("Chatbot response:", response.json())
        except Exception as e:
            print("Error sending to chatbot:", e)

        return f'''
        ✅ Q&A saved in: <code>{qa_path}</code><br>
        ✅ Summary saved in: <code>{context_path}</code><br>
        ✅ Title saved in: <code>{title_path}</code><br>
        Folder name for chatbot/db use: <code>{base_name}</code>
        '''

    return '''
        <form method="post">
            <label>Website URL:</label>
            <input type="text" name="url" placeholder="https://example.com" required>
            <input type="submit" value="Generate Q&A + Summary + Title">
        </form>
    '''

# === Run the Flask app ===
if __name__ == "__main__":
    app.run(debug=True)
