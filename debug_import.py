import sys
import os

# Add src to path like conftest does
sys.path.insert(0, os.path.join('tests', '..', 'src'))

# Print sys.path
print('sys.path:')
for p in sys.path:
    print(' ', p)

# Check if api is already imported
print('api in sys.modules:', 'api' in sys.modules)

# Now try importing main
try:
    import main
    print('main imported successfully')
    print('main file:', main.__file__)
except Exception as e:
    print('Error importing main:', e)
    import traceback
    traceback.print_exc()
