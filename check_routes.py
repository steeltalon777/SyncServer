import os
os.environ['SYNC_TEST_MODE'] = 'stand'
os.environ['SYNC_TEST_ALLOW_STAND'] = '1'

from main import app
for route in app.routes:
    if hasattr(route, 'path') and 'auth' in route.path.lower():
        methods = getattr(route, 'methods', None)
        print(f'{methods or "ANY"} {route.path}')
