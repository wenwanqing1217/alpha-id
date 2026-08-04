"""Start Alpha-ID with correct environment variables."""
import subprocess
import sys
import os

# Set environment variables
env = os.environ.copy()
env["OPENAI_API_KEY"] = "sk-48acbb5b15e24f8187869b832dd050c9"
env["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"
env["SMS_DEMO_MODE"] = "true"
env["ALIPAY_DEMO_MODE"] = "true"

# Start Alpha-ID
subprocess.run(
    [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"],
    env=env,
)
