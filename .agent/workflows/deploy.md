---
description: Deploy the chatbot to production
---

# Deployment Workflow

This workflow guides you through deploying the Inara chatbot.

## Prerequisites

- MongoDB instance (local or cloud like MongoDB Atlas)
- Server with Python 3.8+
- Ollama installed on server (or use cloud LLM API)
- Domain name (optional)

## Steps

1. **Prepare environment**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   Create `.env` file with:
   ```
   FLASK_SECRET_KEY=<random-secret-key>
   EMBED_MODEL=all-MiniLM-L6-v2
   PORT=5000
   MONGODB_URI=<your-mongodb-connection-string>
   ```

3. **Setup Ollama on server**:
   ```bash
   ollama serve &
   ollama pull gemma2:2b
   ```

4. **Run with production server** (Gunicorn):
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 server:app
   ```

5. **Setup reverse proxy** (Nginx example):
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;
       
       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

6. **Setup SSL** (Let's Encrypt):
   ```bash
   certbot --nginx -d yourdomain.com
   ```

## Heroku Deployment

See `ProcFile` in project root. Note: Ollama won't work on Heroku (use cloud LLM instead).

## Docker Deployment (Alternative)

Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "server:app"]
```

## Monitoring

- Check logs for errors
- Monitor Ollama memory usage
- Set up health check endpoint
- Monitor MongoDB connection
