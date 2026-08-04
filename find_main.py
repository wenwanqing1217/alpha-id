import importlib.util
spec = importlib.util.find_spec("main")
print("main.py location:", spec.origin if spec else "NOT FOUND")

# Also check what the installed package has
import alpha_id
print("alpha_id location:", alpha_id.__file__)

# Check settings
from core import settings
print("app_version:", settings.settings.app_version)
