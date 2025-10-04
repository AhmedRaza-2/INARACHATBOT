import requests, re, time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

def normalize_url(url: str) -> str:
    """Ensure consistent URL formatting to avoid duplicates."""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    path = parsed.path.rstrip('/')  # remove trailing slash
    return f"{scheme}://{netloc}{path}"

def crawl_site(start_url, max_pages=4000, max_retries=3):
    """
    Crawl a website starting from start_url, up to max_pages.
    Returns:
        website_text (str) = merged clean text from all crawled pages
        website_title (str) = main site title (from first crawled page)
    """
    visited = set()
    to_visit = [normalize_url(start_url)]
    all_texts = []
    extracted_title = None
    count = 0

    while to_visit and count < max_pages:
        url = to_visit.pop(0)
        url = normalize_url(url)
        if url in visited:
            continue

        for attempt in range(max_retries):
            try:
                print(f"🔎 Crawling ({count+1}/{max_pages}): {url}")
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    print(f"⚠️ Skipped {url} (status {resp.status_code})")
                    raise Exception(f"Status {resp.status_code}")

                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()

                raw_text = " ".join(soup.stripped_strings)
                maybe_title = soup.title.string.strip() if soup.title and soup.title.string else ""
                if not extracted_title and maybe_title:
                    extracted_title = maybe_title

                all_texts.append(raw_text)
                visited.add(url)
                count += 1

                # Add internal links
                for link_tag in soup.find_all("a", href=True):
                    link = normalize_url(urljoin(url, link_tag["href"]))
                    parsed_link = urlparse(link)
                    if parsed_link.netloc == urlparse(start_url).netloc:
                        if link not in visited and link not in to_visit:
                            to_visit.append(link)
                break  # success, exit retry loop

            except Exception as e:
                print(f"⚠️ Failed to crawl {url} (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(1)  # wait before retry

    website_text = "\n\n".join(all_texts)
    return website_text, extracted_title or ""

def clean_domain_name(url: str) -> str:
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path
    domain = domain.replace("www.", "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    return cleaned.strip('_').lower()
