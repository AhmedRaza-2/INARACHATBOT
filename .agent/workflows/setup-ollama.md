---
description: Setup and configure Ollama for the chatbot
---

# Setup Ollama Workflow

This workflow helps you set up Ollama for local LLM inference.

## Steps

1. **Install Ollama** (if not installed):
   - Download from https://ollama.ai/
   - Or use package manager

2. **Start Ollama server**:
   ```bash
   ollama serve
   ```

3. **Pull the required model**:
   ```bash
   ollama pull gemma2:2b
   ```
   
   Alternative (if gemma2 not available):
   ```bash
   ollama pull mistral:7b
   ```

4. **Test the model**:
   ```bash
   ollama run gemma2:2b "Hello, how are you?"
   ```

5. **Keep model warm** (optional):
   - The chatbot uses `keep_alive: 4h` to keep model loaded
   - First request may be slower as model loads into memory

## Configuration

The chatbot is configured in `utilities/llm_utils.py`:
- Default model: `gemma2:2b`
- Fallback: `mistral:7b`
- Auto-detects GPU availability
- Optimized for fast responses

## Troubleshooting

- **Connection refused**: Make sure `ollama serve` is running
- **Model not found**: Pull the model using `ollama pull`
- **Slow responses**: First request loads model (subsequent requests are faster)
- **GPU not detected**: Check NVIDIA drivers if you have a GPU
