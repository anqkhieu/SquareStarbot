import requests, json, os
from dotenv import load_dotenv

load_dotenv()

if False:
    webhook_url = os.environ['LOCAL_SERVER']
else:
    webhook_url = os.environ['WEBHOOK_URL']

print(webhook_url)

data = {'name':'haha', 'url':'tada', 'text': 'this is an example of a webhook'}
r = requests.post(webhook_url, data=json.dumps(data), headers={'Content-Type': 'application/json'})
print(r)
