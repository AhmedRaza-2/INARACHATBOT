"""
Test script for Groq API (FREE and FAST!)
Get your free API key from: https://console.groq.com/keys
"""

import requests
import time

# 👇 PASTE YOUR GROQ API KEY HERE
GROQ_API_KEY = ""

def test_groq():
    """Test Groq API with a simple question."""
    
    if GROQ_API_KEY == "paste-your-groq-key-here":
        print("❌ Please add your Groq API key to this file first!")
        print("Get it from: https://console.groq.com/keys")
        return
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "user", "content": "What is Inara Technologies? Answer in 2 sentences."}
        ],
        "temperature": 0.7,
        "max_tokens": 150,
    }
    
    print("🚀 Testing Groq API...")
    print("=" * 50)
    
    start = time.time()
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        
        elapsed = round(time.time() - start, 2)
        
        print(f"✅ SUCCESS!")
        print(f"⏱️  Response time: {elapsed} seconds")
        print(f"📝 Response:\n{answer}")
        print("=" * 50)
        print("🎉 Groq API is working! You can use this key in your chatbot.")
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ API Error: {e}")
        print(f"Response: {e.response.text}")
        print("\n💡 Check if your API key is correct")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_groq()
