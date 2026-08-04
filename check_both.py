import sys
sys.path.insert(0, "src")

# Import correctly using the package path
from src.main import app

print("App version (from settings):", app.version)
print()
print("All routes with 'agent' in path:")
for r in app.routes:
    if hasattr(r, 'path') and 'agent' in r.path:
        print(f"  {r.path} [{','.join(r.methods)}]")

print()
print("Total routes:", len([r for r in app.routes if hasattr(r, 'path')]))
