#!/usr/bin/env python3
"""
EragAPI - Unified AI Service with proper SSE streaming support
"""

# Standard library imports
import os
import sys
import argparse
import uvicorn
import threading
import signal
import asyncio
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Third-party imports
import google.generativeai as genai
import cohere
import requests
import subprocess
import pystray
from PIL import Image, ImageDraw
from groq import Groq
from openai import OpenAI

load_dotenv()

class BaseClient:
    def chat(self, messages, temperature, max_tokens, stream):
        raise NotImplementedError
    
    def complete(self, prompt, temperature, max_tokens, stream):
        raise NotImplementedError

class GroqClient(BaseClient):
    def __init__(self, model="mixtral-8x7b-32768"):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return completion if stream else completion.choices[0].message.content

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        completion = self.client.completions.create(
            model=self.model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return completion if stream else completion.choices[0].text

class GeminiClient(BaseClient):
    def __init__(self, model="gemini-pro"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(model)

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        # Convert "assistant" role to "model" which Gemini expects
        formatted = [{"role": "model" if m["role"] == "assistant" else "user", 
                     "parts": [{"text": m["content"]}]} for m in messages]
        response = self.model.generate_content(
            formatted,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            stream=stream
        )
        return response if stream else response.text

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            stream=stream
        )
        return response if stream else response.text

class CohereClient(BaseClient):
    def __init__(self, model="command"):
        # Use ClientV2 instead of Client for v2 API
        self.client = cohere.ClientV2(api_key=os.getenv("CO_API_KEY"))
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        # Convert messages to v2 format
        formatted_messages = []
        for msg in messages:
            # Convert roles: "user" -> "user", "assistant" -> "assistant"
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        if stream:
            # Use chat_stream for streaming
            stream = self.client.chat_stream(
                model=self.model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return stream
        else:
            # Use chat for non-streaming
            response = self.client.chat(
                model=self.model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            # Access response text via message.content[0].text in v2
            return response.message.content[0].text

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        # Convert prompt to message format
        messages = [{"role": "user", "content": prompt}]
        
        if stream:
            return self.client.chat_stream(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        else:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.message.content[0].text
        
class DeepSeekClient(BaseClient):
    def __init__(self, model="deepseek-chat"):
        self.client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("DEEPSEEK_API_KEY")
        )
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return response if stream else response.choices[0].message.content

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens, stream)

class MoonshotClient(BaseClient):
    def __init__(self, model="kimi-k2-0905-preview"):
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            raise ValueError("MOONSHOT_API_KEY not found in environment variables")
        
        # Updated to use the correct base URL from the official documentation
        self.client = OpenAI(
            base_url="https://api.moonshot.ai/v1",  # Corrected base URL
            api_key=api_key
        )
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            return response if stream else response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Moonshot API error: {e}")

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens, stream)

class OllamaClient(BaseClient):
    def __init__(self, model="llama2"):
        self.client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return response if stream else response.choices[0].message.content

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        response = self.client.completions.create(
            model=self.model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        return response if stream else response.choices[0].text

class ZAIClient(BaseClient):
    def __init__(self, model="glm-4.5-flash"):
        api_key = os.getenv("ZAI_API_KEY")
        if not api_key:
            raise ValueError("ZAI_API_KEY not found in environment variables")
        
        # Updated to use the correct base URL from Z.ai documentation
        self.client = OpenAI(
            base_url="https://api.z.ai/api/paas/v4/",
            api_key=api_key
        )
        self.model = model

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            return response if stream else response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Z.ai API error: {e}")

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens, stream)

class EragAPI:
    CLIENTS = {
        "groq": GroqClient,
        "gemini": GeminiClient,
        "cohere": CohereClient,
        "deepseek": DeepSeekClient,
        "moonshot": MoonshotClient,
        "ollama": OllamaClient,
        "z": ZAIClient
    }

    def __init__(self, api_type, model=None):
        self.client = self.CLIENTS[api_type](model or self.default_model(api_type))

    @staticmethod
    def default_model(api_type):
        return {
            "groq": "mixtral-8x7b-32768",
            "gemini": "gemini-pro",
            "cohere": "command",
            "deepseek": "deepseek-chat",
            "moonshot": "kimi-k2-0905-preview",
            "ollama": "llama2",
            "z": "glm-4.5-flash"
        }[api_type]

    def chat(self, messages, temperature=0.7, max_tokens=None, stream=False):
        return self.client.chat(messages, temperature, max_tokens, stream)

    def complete(self, prompt, temperature=0.7, max_tokens=None, stream=False):
        return self.client.complete(prompt, temperature, max_tokens, stream)

app = FastAPI(title="EragAPI", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    model: str
    messages: list
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = None

class GenerateRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int = None

def parse_model_string(model_string):
    """Parse model string in format 'provider-model_name' where model_name may contain hyphens"""
    # Known providers
    providers = ["groq", "gemini", "cohere", "deepseek", "moonshot", "ollama", "z"]
    
    for provider in providers:
        if model_string.startswith(provider + "-"):
            # Extract the model name after the provider prefix
            model_name = model_string[len(provider) + 1:]
            return provider, model_name
    
    # If no known provider found, try to split by first hyphen as fallback
    parts = model_string.split("-", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return model_string, None

def format_sse_chunk(chunk):
    """Format a streaming chunk into proper SSE format."""
    # Handle OpenAI/Groq style completion chunks
    if hasattr(chunk, 'choices'):
        try:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content is not None:
                    # Format as SSE with JSON payload
                    data = {
                        "choices": [{
                            "delta": {"content": delta.content},
                            "index": 0,
                            "finish_reason": chunk.choices[0].finish_reason
                        }],
                        "id": getattr(chunk, 'id', 'chatcmpl-default'),
                        "object": "chat.completion.chunk",
                        "created": getattr(chunk, 'created', 0),
                        "model": getattr(chunk, 'model', 'unknown')
                    }
                    return f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            print(f"Error formatting OpenAI chunk: {e}")
    
    # Handle Gemini responses
    if hasattr(chunk, 'text'):
        try:
            # Gemini yields text directly
            return f"data: {json.dumps({'choices': [{'delta': {'content': chunk.text}, 'index': 0}]})}\n\n"
        except:
            return f"data: {json.dumps({'text': str(chunk.text)})}\n\n"
    
    # Handle Cohere responses
    if hasattr(chunk, 'event_type'):
        try:
            if chunk.event_type == 'text-generation':
                return f"data: {json.dumps({'choices': [{'delta': {'content': chunk.text}, 'index': 0}]})}\n\n"
            elif chunk.event_type == 'stream-end':
                return "data: [DONE]\n\n"
        except:
            pass
    
    # Handle plain text responses
    if isinstance(chunk, str):
        return f"data: {json.dumps({'choices': [{'delta': {'content': chunk}, 'index': 0}]})}\n\n"
    
    # Handle other iterable responses (like from Gemini)
    if hasattr(chunk, '__iter__') and not isinstance(chunk, (str, bytes)):
        try:
            for part in chunk:
                if hasattr(part, 'text'):
                    return f"data: {json.dumps({'choices': [{'delta': {'content': part.text}, 'index': 0}]})}\n\n"
        except:
            pass
    
    # Last resort: convert to string
    chunk_str = str(chunk)
    if chunk_str and chunk_str != 'None':
        return f"data: {json.dumps({'choices': [{'delta': {'content': chunk_str}, 'index': 0}]})}\n\n"
    
    return ""

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # Parse the model string properly
        provider, model_name = parse_model_string(request.model)
        
        if not model_name:
            raise HTTPException(400, f"Invalid model format: {request.model}")
        
        if provider not in EragAPI.CLIENTS:
            raise HTTPException(400, f"Unknown provider: {provider}")
        
        erag = EragAPI(provider, model_name)
        
        if request.stream:
            def stream_generator():
                try:
                    stream = erag.chat(request.messages, request.temperature, request.max_tokens, True)
                    
                    # Different providers return different stream types
                    if provider == "gemini":
                        # Gemini returns a generator that yields chunks with text
                        for chunk in stream:
                            if hasattr(chunk, 'text') and chunk.text:
                                formatted = f"data: {json.dumps({'choices': [{'delta': {'content': chunk.text}, 'index': 0}]})}\n\n"
                                yield formatted
                            elif hasattr(chunk, 'parts'):
                                for part in chunk.parts:
                                    if hasattr(part, 'text') and part.text:
                                        formatted = f"data: {json.dumps({'choices': [{'delta': {'content': part.text}, 'index': 0}]})}\n\n"
                                        yield formatted
                    elif provider == "cohere":
                        # Updated Cohere v2 streaming format handling
                        for chunk in stream:
                            if chunk and hasattr(chunk, 'type'):
                                if chunk.type == 'content-delta':
                                    # Extract text from v2 streaming format
                                    content = chunk.delta.message.content.text
                                    formatted = f"data: {json.dumps({'choices': [{'delta': {'content': content}, 'index': 0}]})}\n\n"
                                    yield formatted
                                elif chunk.type == 'stream-end':
                                    break
                    else:
                        # OpenAI-compatible format (Groq, DeepSeek, Moonshot, Ollama, Z.ai)
                        for chunk in stream:
                            formatted = format_sse_chunk(chunk)
                            if formatted:
                                yield formatted
                    
                    # Send completion signal
                    yield "data: [DONE]\n\n"
                    
                except Exception as e:
                    print(f"Streaming error: {e}")
                    error_msg = {"error": str(e)}
                    yield f"data: {json.dumps(error_msg)}\n\n"
            
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        
        # Non-streaming response
        response = erag.chat(request.messages, request.temperature, request.max_tokens)
        return {"message": response}
        
    except Exception as e:
        print(f"Chat endpoint error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/generate")
async def generate_endpoint(request: GenerateRequest):
    try:
        # Parse the model string properly
        provider, model_name = parse_model_string(request.model)
        
        if not model_name:
            raise HTTPException(400, f"Invalid model format: {request.model}")
        
        if provider not in EragAPI.CLIENTS:
            raise HTTPException(400, f"Unknown provider: {provider}")
        
        erag = EragAPI(provider, model_name)
        
        if request.stream:
            def stream_generator():
                try:
                    stream = erag.complete(request.prompt, request.temperature, request.max_tokens, True)
                    
                    # Handle different streaming formats
                    if provider == "gemini":
                        for chunk in stream:
                            if hasattr(chunk, 'text') and chunk.text:
                                formatted = f"data: {json.dumps({'text': chunk.text})}\n\n"
                                yield formatted
                    elif provider == "cohere":
                        for chunk in stream:
                            if hasattr(chunk, 'text'):
                                formatted = f"data: {json.dumps({'text': chunk.text})}\n\n"
                                yield formatted
                    else:
                        # OpenAI-compatible format
                        for chunk in stream:
                            if hasattr(chunk, 'choices'):
                                if chunk.choices and chunk.choices[0].text:
                                    formatted = f"data: {json.dumps({'text': chunk.choices[0].text})}\n\n"
                                    yield formatted
                            elif isinstance(chunk, str):
                                formatted = f"data: {json.dumps({'text': chunk})}\n\n"
                                yield formatted
                    
                    yield "data: [DONE]\n\n"
                    
                except Exception as e:
                    print(f"Generate streaming error: {e}")
                    error_msg = {"error": str(e)}
                    yield f"data: {json.dumps(error_msg)}\n\n"
            
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        
        # Non-streaming response
        response = erag.complete(request.prompt, request.temperature, request.max_tokens)
        return {"response": response}
        
    except Exception as e:
        print(f"Generate endpoint error: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/models/{provider}")
async def get_models_endpoint(provider: str):
    """Get available models for a specific provider"""
    try:
        if provider not in EragAPI.CLIENTS:
            raise HTTPException(404, f"Provider '{provider}' not found")
        
        models = get_available_models(provider)
        return {"provider": provider, "models": models}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/models")
async def get_all_models_endpoint():
    """Get available models for all providers"""
    try:
        all_models = {}
        for provider in EragAPI.CLIENTS.keys():
            models = get_available_models(provider)
            if models:  # Only include providers that have models
                all_models[provider] = models
        return {"models": all_models}
    except Exception as e:
        raise HTTPException(500, str(e))

def create_tray_icon():
    def create_image():
        image = Image.new("RGB", (64, 64), "#3b82f6")
        dc = ImageDraw.Draw(image)
        dc.rectangle([10, 10, 54, 54], fill="white")
        dc.rectangle([20, 20, 30, 44], fill="#3b82f6")
        dc.rectangle([20, 20, 44, 30], fill="#3b82f6")
        dc.rectangle([20, 34, 44, 44], fill="#3b82f6")
        return image

    icon = pystray.Icon("eragapi", create_image(), "ERAG API", menu=pystray.Menu(
        pystray.MenuItem("Quit", lambda: (icon.stop(), os.kill(os.getpid(), signal.SIGTERM)))
    ))
    icon.run()

def start_server(host, port, tray=False):
    if tray:
        threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": host, "port": port}, daemon=True).start()
        create_tray_icon()
    else:
        uvicorn.run(app, host=host, port=port)

def get_available_models(api_type):
    try:
        if api_type == "ollama":
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error listing Ollama models: {result.stderr}")
                return []
            models = [model.split()[0] for model in result.stdout.strip().split('\n')[1:] 
                     if model.split() and model.split()[0] not in ['failed', 'NAME']]
            return models
        
        elif api_type == "groq":
            if not os.getenv("GROQ_API_KEY"):
                return []
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            return [model.id for model in client.models.list().data]
        
        elif api_type == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                return []
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            models = []
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    # Extract just the model name (e.g., "gemini-pro" from "models/gemini-pro")
                    model_name = model.name.split('/')[-1] if '/' in model.name else model.name
                    models.append(model_name)
            return models
        
        elif api_type == "cohere":
            if not os.getenv("CO_API_KEY"):
                return []
            # Use ClientV2 for model listing
            client = cohere.ClientV2(api_key=os.getenv("CO_API_KEY"))
            # For v2, we'll return a list of known models
            # You can customize this list based on your needs
            return ["command", "command-nightly", "command-light", "command-light-nightly"]
        
        elif api_type == "deepseek":
            if not os.getenv("DEEPSEEK_API_KEY"):
                return []
            # Return both chat and reasoner models
            return ["deepseek-chat", "deepseek-reasoner"]
        
        elif api_type == "moonshot":
            api_key = os.getenv("MOONSHOT_API_KEY")
            if not api_key:
                return []
            
            # Try direct HTTP request first with the corrected base URL
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            try:
                # Test the models endpoint with the corrected base URL
                response = requests.get(
                    "https://api.moonshot.ai/v1/models",  # Corrected base URL
                    headers=headers
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    return [model['id'] for model in models_data.get('data', [])]
                else:
                    # Try a minimal chat completion to test the API key with the corrected base URL
                    chat_data = {
                        "model": "kimi-k2-0905-preview",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "max_tokens": 5
                    }
                    
                    chat_response = requests.post(
                        "https://api.moonshot.ai/v1/chat/completions",  # Corrected base URL
                        headers=headers,
                        json=chat_data
                    )
                    
                    # If both tests fail, return updated fallback models
                    return ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-0905-preview"]
                    
            except Exception:
                # Return fallback models if there's an error
                return ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-0905-preview"]
        
        elif api_type == "z":
            # Hardcoded list of Z.ai models based on their documentation
            return [
                "glm-4.5",           # Latest flagship model
                "glm-4.5-flash",     # Fast version of GLM-4.5
                "glm-4.5v",          # Visual model
                "glm-4.5-air",       # Efficient version
                "glm-4.5-airx",      # Enhanced efficient version
                "glm-4-32b-0414-128k", # Cost-effective model with large context
                "glm-4",             # Previous generation
                "glm-4-air",         # Efficient version of GLM-4
                "glm-4-airx",        # Enhanced efficient version of GLM-4
                "glm-3-turbo"        # Older model
            ]
        
        else:
            return []
            
    except Exception as e:
        print(f"Error getting models for {api_type}: {str(e)}")
        return []

def main():
    parser = argparse.ArgumentParser(description="EragAPI - Unified AI Service")
    parser.add_argument("--api", choices=EragAPI.CLIENTS.keys(), help="API provider override")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=11436)
    serve_parser.add_argument("--tray", action="store_true")
    
    # Model command
    model_parser = subparsers.add_parser("model", help="Model operations")
    model_subparsers = model_parser.add_subparsers(dest="model_command")
    
    # List subcommand
    list_parser = model_subparsers.add_parser("list", help="List available models")
    list_parser.add_argument("--api", choices=EragAPI.CLIENTS.keys(), help="Only list models for specific API")
    
    args = parser.parse_args()
    
    if args.command == "serve":
        start_server(args.host, args.port, args.tray)
    elif args.command == "model" and args.model_command == "list":
        api_to_check = []
        if hasattr(args, 'api') and args.api:
            api_to_check = [args.api]
        else:
            api_to_check = EragAPI.CLIENTS.keys()
        
        for api_type in api_to_check:
            print(f"{api_type.upper()} models:")
            models = get_available_models(api_type)
            if models:
                for model in models:
                    print(f"  - {model}")
            else:
                print(f"  - {EragAPI.default_model(api_type)} (default)")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()