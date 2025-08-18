import requests

prompt = "hlo how are you?"

r = requests.post(
    "http://103.176.204.44/api/generate",  # no :5000
    auth=("testbot", "test@123"),
    json={"model": "llama3:instruct", "prompt": prompt, "stream": False}
)

print(r.status_code, r.text)
