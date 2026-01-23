---
description: Debug common chatbot issues
---

# Debug Issues Workflow

This workflow helps you debug common issues with the chatbot.

## Common Issues & Solutions

### 1. "Server not responding" Error

**Symptoms**: Chat returns "❌ Server not responding"

**Debug steps**:
1. Check if Ollama is running:
   ```bash
   curl http://localhost:11434/api/tags
   ```
2. Check Ollama logs for errors
3. Verify model is available:
   ```bash
   ollama list
   ```
4. Test model directly:
   ```bash
   ollama run gemma2:2b "test"
   ```

### 2. Slow Response Times

**Symptoms**: Chat takes 10+ seconds to respond

**Solutions**:
- First request is slow (model loading) - subsequent requests faster
- Reduce `num_predict` in `llm_utils.py` (currently 64)
- Use smaller model like `gemma2:2b` instead of `mistral:7b`
- Check GPU is being used (if available)
- Increase `keep_alive` to keep model warm longer

### 3. "No data found for this domain"

**Symptoms**: Error when trying to chat

**Debug steps**:
1. Check if website was crawled:
   - Look for data in MongoDB
   - Check `base_name` matches
2. Re-crawl the website:
   - Go to `/` and re-enter URL
3. Check MongoDB connection
4. Verify FAISS index was created

### 4. MongoDB Connection Errors

**Symptoms**: Database errors in logs

**Solutions**:
- Check MongoDB is running
- Verify connection string in `.env`
- Check network connectivity
- Verify database permissions

### 5. Widget Not Loading

**Symptoms**: Widget doesn't appear on website

**Debug steps**:
1. Check browser console for errors
2. Verify domain matches in embed code
3. Check CORS settings
4. Test widget endpoint directly: `/widget/<domain>`
5. Verify chatbot data exists for domain

## Debugging Tools

### Check Server Logs
```bash
tail -f server.log
```

### Test API Endpoints
```bash
# Test widget greet
curl -X POST http://localhost:5000/api/widget/greet \
  -H "Content-Type: application/json" \
  -d '{"domain":"example.com"}'

# Test widget chat
curl -X POST http://localhost:5000/api/widget/chat \
  -H "Content-Type: application/json" \
  -d '{"domain":"example.com","message":"Hello"}'
```

### Monitor Ollama
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Monitor Ollama logs
journalctl -u ollama -f
```

## Performance Profiling

Add timing logs in `llm_utils.py` to track:
- Model load time
- Token generation time
- Total response time
