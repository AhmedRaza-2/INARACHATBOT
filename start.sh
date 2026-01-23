#!/bin/bash

# Check if required environment variables are set
if [ -z "$MONGO_URI" ]; then
    echo "ERROR: MONGO_URI environment variable is not set"
    echo "Please set it in your deployment platform's environment variables"
    exit 1
fi

if [ -z "$GEMINI_API_KEY" ]; then
    echo "WARNING: GEMINI_API_KEY is not set. The chatbot may not work properly."
fi

# Start gunicorn
exec gunicorn --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    server:app
