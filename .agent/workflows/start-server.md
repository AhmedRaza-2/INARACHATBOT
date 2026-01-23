---
description: Start the Flask development server
---

# Start Server Workflow

This workflow starts the Flask chatbot server.

## Steps

1. Ensure you're in the project directory
2. Activate virtual environment (if using one)
3. Run the server:
   ```bash
   python server.py
   ```
4. Server will start on `http://localhost:5000`
5. Access the chatbot at `http://localhost:5000/`

## Environment Variables Required

- `FLASK_SECRET_KEY` - Secret key for Flask sessions
- `EMBED_MODEL` - Embedding model name (default: all-MiniLM-L6-v2)
- `PORT` - Server port (default: 5000)
- MongoDB connection settings

## Notes

- Make sure Ollama is running (`ollama serve`) for LLM responses
- MongoDB should be accessible for data storage
