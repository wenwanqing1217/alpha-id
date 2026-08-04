import os
import sys

# Check if agent route exists in the running code
sys.path.insert(0, os.path.dirname(__file__))
from src.main import app

print("Checking for agent/chat route...")
found = False
for r in app.routes:
    if hasattr(r, 'path') and r.path == '/api/v1/agent/chat':
        print(f"  FOUND: {r.path} [{','.join(r.methods)}]")
        found = True

if not found:
    print("  NOT FOUND - agent/chat route is missing!")

# Check what the running Alpha-ID on port 8000 actually has
import urllib.request
import json
try:
    req = urllib.request.Request('http://localhost:8000/openapi.json')
    with urllib.request.urlopen(req, timeout=5) as resp:
        spec = json.loads(resp.read())
        paths = list(spec.get('paths', {}).keys())
        print(f"\nRunning Alpha-ID has {len(paths)} routes:")
        for p in sorted(paths):
            print(f"  {p}")
except Exception as e:
    print(f"\nCannot reach running Alpha-ID: {e}")
