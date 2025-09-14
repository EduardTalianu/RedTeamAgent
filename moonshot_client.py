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
        """List available models from Moonshot API using the same approach as eragAPI."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # Try to get models from the API first
            response = requests.get(
                f"{self.base_url}/models", 
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                model_ids = [model.get("id") for model in data.get("data", [])]
                if model_ids:
                    return model_ids
            
            # If models endpoint doesn't work, try a test chat completion to verify API key
            test_payload = {
                "model": "moonshot-v1-32k",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5
            }
            
            test_response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=test_payload,
                timeout=10
            )
            
            # If the API key works, return comprehensive model list
            if test_response.status_code == 200:
                return [
                    "moonshot-v1-8k",
                    "moonshot-v1-32k", 
                    "moonshot-v1-128k",
                    "moonshot-v1-auto"
                    "kimi-k2-0905-preview"
                ]
                
        except requests.exceptions.RequestException as e:
            print(f"Request error during model listing: {e}")
        except json.JSONDecodeError as e:
            print(f"JSON decode error during model listing: {e}")
        except Exception as e:
            print(f"General error during model listing: {e}")
        
        # Return fallback models if all else fails
        return [
            "moonshot-v1-8k",
            "moonshot-v1-32k", 
            "moonshot-v1-128k",
            "moonshot-v1-auto"
            "kimi-k2-0905-preview"
        ]