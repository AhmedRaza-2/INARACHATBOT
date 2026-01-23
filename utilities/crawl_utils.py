from pymongo import MongoClient
import requests, re, time, os,certifi, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    path = parsed.path.rstrip('/')
    return f"{scheme}://{netloc}{path}"

def fetch_sitemap_urls(start_url):
    """Fetch all URLs from sitemap.xml if it exists."""
    parsed = urlparse(start_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    
    try:
        print(f"🗺️  Checking for sitemap at: {sitemap_url}")
        resp = requests.get(sitemap_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        
        if resp.status_code == 200:
            # Parse XML sitemap
            root = ET.fromstring(resp.content)
            
            # Handle both with and without namespace
            urls = set()
            # Try with namespace
            for url_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                if url_elem.text:
                    urls.add(normalize_url(url_elem.text))
            
            # Try without namespace (fallback)
            if not urls:
                for url_elem in root.findall('.//loc'):
                    if url_elem.text:
                        urls.add(normalize_url(url_elem.text))
            
            if urls:
                print(f"✅ Found {len(urls)} URLs in sitemap")
                return urls
            else:
                print(f"⚠️  Sitemap found but no URLs extracted")
                return set()
        else:
            print(f"ℹ️  No sitemap found (status {resp.status_code})")
            return set()
    except Exception as e:
        print(f"ℹ️  Could not fetch sitemap: {e}")
        return set()

def crawl_single_page(url, start_url, timeout=15, max_retries=3):
    """Fetch and extract text + links from one page."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                raise Exception(f"Status {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            raw_text = " ".join(soup.stripped_strings)
            maybe_title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Extract internal links
            links = set()
            for link_tag in soup.find_all("a", href=True):
                link = normalize_url(urljoin(url, link_tag["href"]))
                parsed_link = urlparse(link)
                if parsed_link.netloc == urlparse(start_url).netloc:
                    links.add(link)

            # Log successful crawl
            print(f"✅ Crawled: {url}")
            return raw_text, maybe_title, links

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Failed {url} after {max_retries} attempts: {e}")
            time.sleep(0.5)
    return "", "", set()


def crawl_site(start_url, max_pages=4000, max_workers=20):
    """
    Crawl a website concurrently. First checks sitemap.xml for all URLs.
    Returns:
        (website_text, website_title)
    """
    visited = set()
    to_visit = {normalize_url(start_url)}
    all_texts = []
    extracted_title = None
    count = 0

    print(f"\n{'='*80}")
    print(f"🚀 Starting crawl for: {start_url}")
    print(f"📊 Max pages: {max_pages} | Workers: {max_workers}")
    print(f"{'='*80}\n")
    
    # Try to fetch sitemap URLs first
    sitemap_urls = fetch_sitemap_urls(start_url)
    if sitemap_urls:
        # Add sitemap URLs to the queue
        for url in sitemap_urls:
            if len(to_visit) + len(visited) < max_pages:
                to_visit.add(url)
        print(f"📋 Added {len(sitemap_urls)} URLs from sitemap to crawl queue\n")
    
    start_time = time.time()

    while to_visit and count < max_pages:
        urls_batch = list(to_visit)[:max_workers]
        to_visit -= set(urls_batch)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(crawl_single_page, url, start_url): url for url in urls_batch}

            for future in as_completed(futures):
                url = futures[future]
                try:
                    raw_text, maybe_title, new_links = future.result()
                    if not raw_text:
                        continue
                    visited.add(url)
                    all_texts.append(raw_text)
                    count += 1

                    # Show progress
                    print(f"📄 [{count}/{max_pages}] Pages crawled so far | Queue: {len(to_visit)} remaining")

                    if not extracted_title and maybe_title:
                        extracted_title = maybe_title
                        print(f"📌 Website title: {maybe_title}")

                    # Add new links (not yet visited)
                    new_links_added = 0
                    for link in new_links:
                        if link not in visited and len(visited) + len(to_visit) < max_pages:
                            to_visit.add(link)
                            new_links_added += 1
                    
                    if new_links_added > 0:
                        print(f"🔗 Found {new_links_added} new links to crawl")

                except Exception as e:
                    print(f"❌ Error for {url}: {e}")

    total_time = round(time.time() - start_time, 2)
    print(f"\n{'='*80}")
    print(f"✅ Crawl completed!")
    print(f"📊 Total pages: {count} | Time: {total_time}s | Avg: {round(total_time/count, 2)}s/page")
    print(f"{'='*80}\n")

    website_text = "\n\n".join(all_texts)
    return website_text, extracted_title or ""


def check_existing_data(base_name: str) -> bool:
    """
    Check if the given website already has stored title, summary, chunks, or FAISS index.
    Works with per-domain databases (e.g., abc_com.title, abc_com.chunks, etc.)
    """
    client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
    db_name = base_name.replace(".", "_")
    db = client[db_name]

    has_title = db.title.count_documents({}) > 0
    has_summary = db.summary.count_documents({}) > 0
    has_chunks = db.chunks.count_documents({}) > 0
    has_index = db.faiss_index.count_documents({}) > 0

    if has_title or has_summary or has_chunks or has_index:
        print(f"🔎 Existing data found for {base_name} → skipping crawl.")
        return True
    print(f"🌐 No existing data found for {base_name} → will crawl.")
    return False

def clean_domain_name(url: str) -> str:
    parsed_url = urlparse(url)
    domain = parsed_url.netloc or parsed_url.path
    domain = domain.replace("www.", "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    return cleaned.strip('_').lower()
