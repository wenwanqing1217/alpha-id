"""Start Alpha-ID on port 8002."""
import os
import sys

# Set environment variables
os.environ["AUTH_MASTER_KEY"] = "f81a6c0b2543f619d921b8f1501829a342e10aa44972061d145f8eaece650532"
os.environ["OPENAI_API_KEY"] = "sk-faa4a03391ef432b811034e664bb1a30"
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com"

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8002, log_level="info")
