import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
os.environ.setdefault('AUTH_MASTER_KEY', 'test-master-key-256bit-secret-for-service-only')

import uvicorn
from main import app

if __name__ == '__main__':
    print('Starting AID service on http://127.0.0.1:8005')
    uvicorn.run(app, host='127.0.0.1', port=8005, log_level='warning')
