from flask import Flask, request, abort
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed
import os

# Setup
app = Flask(__name__)
load_dotenv()
DEBUG = True

# Webapp
@app.route('/')
def index():
  return '<h1><center>This web server is receiving webhooks for your Square orders.</center></h1>'

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        handle_webhook(request.json)
        return 'Success', 200
    else:
        abort(400)

def handle_webhook(json):
    if DEBUG: print('Received', json['type'])

    if json['type'] == 'payment.created':
        object = json['data']['object']['payment']
        if DEBUG: print(object)

        title = "🛍️  New Store Order Received!"
        amount = '{:.2f}'.format(object['total_money']['amount'] * 0.01)
        order_url = f"https://squareupsandbox.com/dashboard/sales/transactions/{object['order_id']}/"
        description = f"**OrderID:** {object['order_id']} \
            \n**Status:** {object['status'].capitalize()}, {object['source_type'].capitalize()} \
            \n**Amount:** {amount} {object['total_money']['currency']} \
            \n**[>> View Order]({order_url})**"
        color = 6673887
        if object.get('receipt_url') is None:
            footer = f"🧾 Receipt Number: {object['receipt_number']} | Timestamp: {object['created_at'][11:-5]}"
        else:
            footer = f"🧾 View Receipt: [{object['receipt_number']}]({object['receipt_url']}) | Timestamp: {object['created_at'][11:-5]}"
    elif json['type'] == 'refund.created':
        object = json['data']['object']['refund']
        if DEBUG: print(object)

        title = "💸  Refund Request Received"
        amount = '{:.2f}'.format(object['amount_money']['amount'] * 0.01)
        if object.get('reason') is None: reason = 'Left blank.'
        else: reason = object['reason']

        order_url = f"https://squareupsandbox.com/dashboard/sales/transactions/{object['order_id']}/"
        description = f"**OrderID:** {object['order_id']} \
            \n**Status:** {object['status'].capitalize()} \
            \n**Amount:** {amount} {object['amount_money']['currency']} \
            \n**Reason:** {reason} \
            \n**[>> View Order]({order_url})**"
        color = 14377308
        footer = f"🧾 Timestamp: {object['created_at'][11:-5]}"

    webhook = DiscordWebhook(os.getenv('DISCORD_WEBHOOK_URL'))
    embed = DiscordEmbed(title=title, description=description, color=color)
    embed.set_footer(text=footer)
    webhook.add_embed(embed)
    response = webhook.execute()

    if DEBUG: print(response)

if __name__ == '__main__':
    app.run()
