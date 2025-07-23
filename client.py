from flask import Flask, request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
import os
import json
import google.generativeai as genai

# === SETUP GEMINI ===
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs")

app = Flask(__name__)
visited = set()

# === Setup Selenium driver
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    return webdriver.Chrome(options=chrome_options)

# === Check if URL is valid and belongs to base domain
def is_valid(url, base_domain):
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and base_domain in parsed.netloc

# === Extract all internal links from a page
def extract_links(driver, base_url, base_domain):
    soup = BeautifulSoup(driver.page_source, "html.parser")
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = urljoin(base_url, a_tag["href"])
        href = href.split("#")[0].rstrip("/")
        if is_valid(href, base_domain):
            links.add(href)
    return links

# === Get visible body text of the page
def extract_visible_text(driver):
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        return body.text
    except:
        return ""

# === Crawl entire site up to `max_pages`
def crawl_site(start_url, max_pages=30):
    driver = setup_driver()
    base_domain = urlparse(start_url).netloc
    to_visit = [start_url]
    all_text = {}

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue

        try:
            driver.get(url)
            time.sleep(2)

            text = extract_visible_text(driver)
            all_text[url] = text
            visited.add(url)

            links = extract_links(driver, url, base_domain)
            to_visit.extend(link for link in links if link not in visited and link not in to_visit)

        except Exception as e:
            print(f"[-] Failed to load {url}: {e}")
            continue

    driver.quit()
    return all_text

# === Generate Q&A pairs using Gemini
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
  {{"question": "...", "answer": "..."}} ,
  ...
]

Text:
"""{text}"""
'''
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini API Error (QA):", e)
        return "[]"

# === Generate a short 3–5 sentence summary of the website
def generate_website_context(text):
    prompt = f'''
You are an assistant summarizer.

Summarize what this website is about in 3–5 concise sentences. Mention key offerings, services, target users, industries, and any unique points.

Text:
"""{text[:8000]}"""
'''
    try:
        model = genai.GenerativeModel("models/gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print("Gemini API Error (Context):", e)
        return "No summary available."

# === Main route to handle form submission and processing
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if not url:
            return "Please provide a valid URL."

        website_text = crawl_site(url)
        all_combined = "\n\n".join(website_text.values())

        # === Generate outputs
        qa_output = convert_to_qa(all_combined)
        summary_context = generate_website_context(all_combined)

        # === Save files
        base_name = urlparse(url).netloc.replace('.', '_')
        os.makedirs("outputs", exist_ok=True)

        qa_path = os.path.join("outputs", f"{base_name}_qa.json")
        context_path = os.path.join("outputs", f"{base_name}_summary.txt")

        with open(qa_path, "w", encoding="utf-8") as f:
            f.write(qa_output)

        with open(context_path, "w", encoding="utf-8") as f:
            f.write(summary_context)

        return f'''
        ✅ Q&A saved as <code>{qa_path}</code><br>
        ✅ Summary saved as <code>{context_path}</code>
        '''

    return '''
        <form method="post">
            <label>Website URL:</label>
            <input type="text" name="url" placeholder="https://example.com" required>
            <input type="submit" value="Generate Q&A + Summary">
        </form>
    '''

# === Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)
