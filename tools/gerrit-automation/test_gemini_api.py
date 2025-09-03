#!/usr/bin/env python3
"""
Gemini API Debugging Tool

Tests Gemini API access and helps debug common issues:
- Invalid API key
- API not enabled
- Model availability
- Authentication problems
"""

import requests
import json
import sys

def test_gemini_api(api_key: str):
    """Test Gemini API and diagnose issues"""
    
    print(f"🔍 Testing Gemini API with key: {api_key[:8]}...{api_key[-4:]}")
    
    # Test 1: Check if API key format is correct
    print("\n1. 🔑 API Key Format Check:")
    if not api_key.startswith('AIza'):
        print("❌ Invalid API key format - should start with 'AIza'")
        return False
    else:
        print("✅ API key format looks correct")
    
    # Test 2: List available models
    print("\n2. 📋 Available Models Check:")
    models_url = f'https://generativelanguage.googleapis.com/v1beta/models?key={api_key}'
    
    try:
        response = requests.get(models_url, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            print(f"✅ Found {len(models)} available models:")
            for model in models[:5]:  # Show first 5
                print(f"   - {model}")
            return True
        
        elif response.status_code == 403:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', '')
            
            if 'API key not valid' in error_msg:
                print("❌ API key is invalid")
                print("   💡 Solution: Generate new key at https://makersuite.google.com/app/apikey")
                
            elif 'has not been used' in error_msg or 'API_KEY_INVALID' in error_msg:
                print("❌ API key never used or disabled")
                print("   💡 Solution: Make a test request from Google AI Studio first")
                
            elif 'not enabled' in error_msg or 'PERMISSION_DENIED' in error_msg:
                print("❌ Generative AI API not enabled")
                print("   💡 Solution: Enable API in Google Cloud Console:")
                print("      1. Go to: https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com")
                print("      2. Click 'Enable API'") 
                print("      3. Wait a few minutes for activation")
                
            else:
                print(f"❌ API access denied: {error_msg}")
            
            return False
            
        elif response.status_code == 404:
            print("❌ API endpoint not found")
            print("   💡 Possible causes:")
            print("      - Wrong API URL (should be generativelanguage.googleapis.com)")
            print("      - API version changed (currently using v1beta)")
            return False
            
        else:
            print(f"❌ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Network connection failed")
        return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def test_simple_generation(api_key: str, model: str = 'gemini-2.5-flash'):
    """Test simple text generation"""
    print(f"\n3. 🧪 Simple Generation Test ({model}):")
    
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    
    data = {
        'contents': [{
            'parts': [{'text': 'Say "Hello World" and nothing else.'}]
        }]
    }
    
    try:
        response = requests.post(url, json=data, timeout=15)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ Generation successful: {text.strip()}")
                return True
            else:
                print("❌ No content in response")
                return False
        else:
            error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
            error_msg = error_data.get('error', {}).get('message', response.text[:100])
            print(f"❌ Generation failed: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ Generation test failed: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 test_gemini_api.py <api_key>")
        print("Example: python3 test_gemini_api.py AIzaSyD...")
        sys.exit(1)
    
    api_key = sys.argv[1]
    
    print("🧪 Gemini API Diagnostic Tool")
    print("=" * 40)
    
    # Run all tests
    key_ok = test_gemini_api(api_key)
    
    if key_ok:
        test_simple_generation(api_key)
    
    print("\n" + "=" * 40)
    
    if key_ok:
        print("✅ Gemini API is working - you can use it in gerrit_ai_automated.py")
    else:
        print("❌ Gemini API has issues - fix the problems above first")

if __name__ == "__main__":
    main()
