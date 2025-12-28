#!/bin/bash
set -e

echo "Starting Ollama service initialization..."

# Wait for Ollama to be ready
sleep 10

# Pull the Mistral model
echo "Pulling Mistral model..."
ollama pull mistral

echo "Model initialization complete!"