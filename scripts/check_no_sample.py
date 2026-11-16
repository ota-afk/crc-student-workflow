import os
import sys

import requests

API_URL = os.getenv('API_URL', 'http://localhost:8000')
# The deployed API needs the key; locally API_KEY is usually empty, so no header is sent.
headers = {'X-API-Key': key} if (key := os.getenv('API_KEY', '').strip()) else {}
response = requests.get(f'{API_URL}/workflow', headers=headers, timeout=10)
# Fail loudly on 401/429/503 instead of checking an error message as if it were a workflow.
response.raise_for_status()
data = response.json()
text = str(data).lower()
problems = []
if data.get('is_mock'):
    problems.append('is_mock is true')
if '(sample)' in text or 'placeholder' in text:
    problems.append('sample or placeholder text found')
for task in data['workflow']:
    task_id = task['id']
    for blocker in task.get('blockers', []):
        if blocker['verification_status'] != 'verified':
            problems.append('unverified blocker on ' + task_id)
print(problems or 'clean')
sys.exit(1 if problems else 0)
