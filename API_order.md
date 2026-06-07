
DELETE
Delete order
https://api.burgerprints.com/v2/order/{id}
Purpose
This API can only be called when the order is in an unpaid status. It is intended solely for deleting an order.

Request Description
This endpoint is used to delete a specific order by sending an HTTP DELETE request to the specified URL.

Request Body
This request does not require a request body.

Response
The response returned a status code of 200 and the content type is application/json. The response body follows the JSON schema:

json
{
    "is_success": boolean,
    "message": "string"
}
The "is_success" field indicates whether the request was successful, and the "message" field provides a description of the error encountered during the processing of the order.

HEADERS
api-key
84877a53-63b9-4ee5-a09e-032ad5e08ab1

Example Request
Delete order
View More
python
import requests

url = "https://api.burgerprints.com/v2/order/A26200-CT-4373685"

payload={}
headers = {
  'api-key': '84877a53-63b9-4ee5-a09e-032ad5e08ab1'
}

response = requests.request("DELETE", url, headers=headers, data=payload)

print(response.text)
200 OK
Example Response
Body
Headers (14)
json
{
  "is_success": true,
  "message": "Order deleted successfully"
}
POST
Charge order
https://api.burgerprints.com/v2/order/charge
Order Charge
This endpoint is used to charge orders.

Request Body
order_ids (array of strings) - The IDs of the orders to be charged.
Response
state (string) - Shows the result of your request.

purchased – the charge was successful

fail – something went wrong

pending – still processing

message (string) - Show a message about the transaction after it's completed.

details (string) - Show the detailed response after the transaction is completed.

Example:

json
{
    "state": "string",
    "reason": {
        "name": "string",
        "message": "string",
        "details": "string",
        "code": 200,
        "method": "string"
    }
   
}
HEADERS
api-key
b388776b-8af8-4f97-b395-35908fc97d97

Content-Type
application/json

Body
raw (json)
json
{
    "order_ids": [
        "A28756-CT-3161831"
    ]
}
Example Request
success
View More
python
import requests
import json

url = "https://api.burgerprints.com/v2/order/charge"

payload = json.dumps({
  "order_ids": [
    "A28896-CT-4604817"
  ]
})
headers = {
  'api-key': 'b388776b-8af8-4f97-b395-35908fc97d97',
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
200 OK
Example Response
Body
Headers (14)
json
{
  "state": "purchased",
  "reason": {
    "name": "Success",
    "message": "Success",
    "details": "Success",
    "code": 200,
    "method": "balance"
  },
  "balance": null
}
POST
Add webhook
https://api.burgerprints.com/notification/api/v1/public/fulfillment/notify/webhook
Notify Webhook Fulfillment API
This API endpoint is used to notify a webhook for fulfillment.

Request
Method: POST

Endpoint: https://api.burgerprints.com/notification/api/v1/public/fulfillment/notify/webhook

Body:

end_point_url (text, required): The URL of the endpoint to be notified.

is_active (text, required): Indicates whether the webhook is active or not.

Response
The response for this request is in text/plain format with a status code of 200. The response body contains the message "Create notify webhook success".

Response JSON Schema
View More
json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "number",
      "description": "The status code of the response"
    },
    "message": {
      "type": "string",
      "description": "The message indicating the result of the request"
    }
  }
}
HEADERS
api-key
b388776b-8af8-4f97-b395-35908fc97d97

Content-Type
application/json

Body
raw (json)
json
{
    "end_point_url": "https://webhook.site/2c82447e-53c1-4f8f-bcca-425c6b9f331f",
    "is_active": false
}