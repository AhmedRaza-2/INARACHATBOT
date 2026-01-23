---
description: Test the chatbot functionality
---

# Test Chatbot Workflow

This workflow helps you test the chatbot end-to-end.

## Steps

1. **Start Ollama** (if not running):
   ```bash
   ollama serve
   ```

2. **Start the Flask server**:
   ```bash
   python server.py
   ```

3. **Access the application**:
   - Open browser to `http://localhost:5000/`

4. **Test the flow**:
   - Enter a website URL and matching email
   - Register/Login with credentials
   - Start a chat session
   - Send test messages
   - Verify RAG retrieval is working
   - Check LLM responses

5. **Test the widget**:
   - Navigate to `/widget-demo`
   - Test embedded widget functionality

## Common Issues

- **Ollama not responding**: Make sure `ollama serve` is running
- **No data found**: Ensure website was crawled and indexed
- **MongoDB errors**: Check MongoDB connection
- **Slow responses**: Check Ollama model is loaded (first request may be slow)
