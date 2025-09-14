# moonshot_client.py - Fixed version with proper model listing
import os
import requests
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class MoonshotClient:
    def __init__(self, api_key=None, model="moonshot-v1-32k"):
        # Try to get API key from parameter first, then from environment
        self.api_key = api_key or os.getenv("MOONSHOT_API_KEY")
        if not self.api_key:
            raise ValueError("MOONSHOT_API_KEY environment variable is required but not set")
        self.model = model
        self.base_url = "https://api.moonshot.ai/v1"
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: Optional[int] = None, stream: bool = False):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=stream,
                timeout=60
            )
            
            if response.status_code != 200:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"Moonshot API error: {response.status_code} - {error_message}")
            
            if stream:
                return response
            else:
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON decode error: {str(e)}")
    
    def list_models(self) -> List[str]:
        """Return the live Moonshot model catalogue."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.get(f"{self.base_url}/models", headers=headers, timeout=10)
            resp.raise_for_status()
            return [m["id"] for m in resp.json()["data"]]
        except Exception as e:
            print(f"[Moonshot] /models failed ({e}) — using fallback")
            # Last-resort fallback (the 12-model set you just confirmed)
            return [
                "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "moonshot-v1-auto",
                "kimi-k2-0711-preview", "kimi-k2-turbo-preview", "kimi-k2-0905-preview",
                "kimi-latest", "moonshot-v1-8k-vision-preview", "moonshot-v1-32k-vision-preview",
                "moonshot-v1-128k-vision-preview", "kimi-thinking-preview"
            ]