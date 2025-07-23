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
import google.generativeai as genai

# === SETUP GEMINI ===
genai.configure(api_key="AIzaSyBg2j-nmkJ7Fm63UeGRPSKJlYVjUzcdchs")  # Replace with your key

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

# === Extract website <title> from the homepage ===
def extract_title(driver):
    try:
        title_element = driver.find_element(By.TAG_NAME, "title")
        title = title_element.get_attribute("innerText")
        return title.replace("-", " ").strip()
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

# === Generate Q&A pairs using Gemini ===
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
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]

        json_data = json.loads(raw)
        return json_data

    except Exception as e:
        print("Gemini API Error (QA):", e)
        return []

# === Generate website summary ===
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

# === Main route ===
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

        # === Clean name for this website and prepare folder ===
        base_name = clean_domain_name(url)
        folder_path = os.path.join("outputs", base_name)
        os.makedirs(folder_path, exist_ok=True)

        qa_path = os.path.join(folder_path, f"{base_name}_qa.json")
        context_path = os.path.join(folder_path, f"{base_name}_summary.txt")
        title_path = os.path.join(folder_path, f"{base_name}_title.txt")

        with open(qa_path, "w", encoding="utf-8") as f:
            json.dump(qa_list, f, indent=2, ensure_ascii=False)

        with open(context_path, "w", encoding="utf-8") as f:
            f.write(summary_context)

        with open(title_path, "w", encoding="utf-8") as f:
            f.write(website_title)

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
