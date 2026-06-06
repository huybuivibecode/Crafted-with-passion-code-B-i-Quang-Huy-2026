
Public
ENVIRONMENT
No Environment
LAYOUT
Double Column
LANGUAGE
Python - Requests
BurgerPrints Api v2.0
Introduction
1. Overview
2. Authentication
Authenticated
Orders
Product
Webhook
Balance
BurgerPrints Api v2.0
1. Overview
The BurgerPrints API v2 is a API service for Get all orders, get a single order, create order and cancel order.
API is created according to Restful API standard. Requests are made using standard of GET, POST and PUT. All responses are JSON.

Once you sign up for an account, you will be provided with a real API key (In your store Preferences).

2. Authentication
This API uses normal method for authentication (API Keys in params). Your private API keys should be used as the password.

If you are currently logged in account settings, you can go to [Fulfillment store] -> [Fulfillment store settings] and get API Keys there.

All requests must be made over HTTPS.

Authenticated
The /authenticated endpoints let you manage information about the authenticated user.

GET
Get authenticated user
https://api.burgerprints.com/v2/authenticated
This HTTP GET request retrieves data from the specified endpoint. The response will include a boolean value indicating the success status, and an optional message string. Here are some example responses:

Response:{ "is_success": true, "message": "The API key is valid."}
HEADERS
api-key
6398d94e-4c4a-4400-be7c-4e05b8bbe79d

Example Request
success
View More
python
import requests

url = "https://api.burgerprints.com/v2/authenticated"

payload={}
headers = {
  'api-key': 'e443f8af-eca2-4a73-8ab2-b287298c3a64'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
200 OK
Example Response
Body
Headers (12)
json
{
  "code": 200,
  "message": "success",
  "data": {
    "is_success": true,
    "message": "The API key is valid."
  }
}
Orders
GET
Get all orders
https://api.burgerprints.com/v2/order
Get all orders
Retrieve information of all orders.
Request Body
No request body.
Request param
sandbox (boolean, required): Set to true to place the order in sandbox mode.

reference(string, optional) field to help you search Burgerprints order

store_id (string, optional) field to help filter order by store_id

state (string, optional) field to help filter order by state

start_date(timestamp, optional) field to help filter order by date time

end_date (timestamp, optional) field to help filter order by date time

page (string) : Number of displayed pages. Default 1

page_size (string) : Maximum number of items to be displayed on one page. Default 50 maximum 500

Example Request
Get all orders
View More
python
import requests

url = "https://api.burgerprints.com/v2/order"

payload={}
headers = {
  'api-key': '3c072273-9a43-44c3-b6ec-778f57cd1c28'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
200 OK
Example Response
Body
Headers (13)
View More
json
{
  "total": 334,
  "data": [
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "15.49",
      "reference_order": "check 2407-04",
      "shipping_fee": "7.99",
      "callback_url": "",
      "shipping": {
        "id": "ECzFw7sZ5Qq2e2zX",
        "name": "David Thomas",
        "email": "olivia@thobox.vn",
        "phone": "4.48E+11",
        "gift": false,
        "address": {
          "line1": "6 Yr Ysfa",
          "line2": "Maesteg",
          "city": "Maesteg",
          "state": "AK",
          "postal_code": "CF34 9AG",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "7.50",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3808777",
      "created_date": "20240724T115004Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "15.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "7.99",
          "design_front_url": "https://cdn.customily.com/ExportFile/vvgears/ecc33d0f-5155-41sdfssfac-949c-83de17ce305a.png",
          "price": "7.50",
          "mockup_front_url": "https://cdn.customily.com/shopify/assetFiles/previews/vvgears.myshopify.com/4da8da08-397c-4ea2-bb51-e12ba4a188ad.jpeg",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "AOsN7auxkND4FdgY"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.24",
      "reference_order": "checkcallAPIbasetheu2",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "WagndmjmaaaixP52",
        "name": "thuancheckcallAPI",
        "email": "dominhthuan.94@gmail.com",
        "phone": "34",
        "gift": false,
        "address": {
          "line1": "1300 Rosa Parks Blvd",
          "line2": "1",
          "city": "1",
          "state": "IN",
          "postal_code": "1",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "18.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3807394",
      "created_date": "20240723T062445Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XS",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "18.75",
          "mockup_front_url": "",
          "base_short_code": "USMEZS1001",
          "currency": "USD",
          "id": "ehrGWVjgvuATa03S"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "89.46",
      "reference_order": "thêu 101",
      "shipping_fee": "14.46",
      "callback_url": "",
      "shipping": {
        "id": "tVIuNai2pZazsgV7",
        "name": "Tom Celillo",
        "email": "",
        "phone": "6506461097",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94406",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "75.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3807351",
      "created_date": "20240723T061256Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "89.46",
          "quantity": "4",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XS",
          "shipping_fee": "14.46",
          "design_front_url": "",
          "price": "18.75",
          "mockup_front_url": "",
          "base_short_code": "USMEZS1001",
          "currency": "USD",
          "id": "di9cLPRaumVgkPwx"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "254.46",
      "reference_order": "thêu 100",
      "shipping_fee": "14.46",
      "callback_url": "",
      "shipping": {
        "id": "BidZbQAqj4wnMWzd",
        "name": "Tom Celillo",
        "email": "",
        "phone": "6506461097",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94406",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "240.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3807345",
      "created_date": "20240723T061146Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "254.46",
          "quantity": "4",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XS",
          "shipping_fee": "14.46",
          "design_front_url": "",
          "price": "60.00",
          "mockup_front_url": "",
          "base_short_code": "USMEZS1001",
          "currency": "USD",
          "id": "3PexhU4WIEqAXbhy"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.24",
      "reference_order": "",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "IFTPRZVwmL6Iou6U",
        "name": "Dr. Török Boróka PhD",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AL",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "18.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3807305",
      "created_date": "20240723T054644Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XS",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "18.75",
          "mockup_front_url": "",
          "base_short_code": "USMEZS1001",
          "currency": "USD",
          "id": "pROhpUKePd7mFZUI"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "12.24",
      "reference_order": "check dash 3",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "1iNjXfv9XSmzZTC7",
        "name": "Tom Celillo",
        "email": "sfsadfdfbhgdh",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94405",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3806700",
      "created_date": "20240722T120112Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "12.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/07/22/ae6409549203054929c0e4a7f587f97f.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/07/22/ae6409549203054929c0e4a7f587f97f.png",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "ya7Wm0qF13LF7gXK"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "94.72",
      "reference_order": "check dash 2",
      "shipping_fee": "14.47",
      "callback_url": "",
      "shipping": {
        "id": "HOYhwIpMlECyzzqJ",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94405",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "80.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3806687",
      "created_date": "20240722T115236Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "94.72",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "14.47",
          "design_front_url": "",
          "price": "26.75",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "hhjMIjGqLyVPfok3"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "31.72",
      "reference_order": "check check..",
      "shipping_fee": "11.47",
      "callback_url": "",
      "shipping": {
        "id": "wzsFQ0qbo61pSEUQ",
        "name": "Tom Celillo",
        "email": "",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94405",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "20.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3806664",
      "created_date": "20240722T113953Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "31.72",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "11.47",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/07/22/7504bd020602e8595688b2669e9dd2d5.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/07/22/a7cec8f3148e73287613f6c6cf077b4a.jpg",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "xARHiP5u4E3LvaPA"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "15.75",
      "reference_order": "checktimeline15",
      "shipping_fee": "0.5",
      "callback_url": "",
      "shipping": {
        "id": "FnMVBDOLlFBaLH4b",
        "name": "RACHEL KOEHN-MORRISON",
        "email": "",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "416 MAPLE LN",
          "line2": "",
          "city": "NORTH ENGLISH",
          "state": "IA",
          "postal_code": "52316-8629",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "15.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3804236",
      "created_date": "20240719T113219Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "15.75",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "3XL",
          "shipping_fee": "0.50",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/07/19/ead9015d6ba75a1b67cdc8a9c3fd78a8.png",
          "price": "15.25",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/07/19/b0f2694046ac812ea23a46483fdf21de.jpg",
          "base_short_code": "USMCC1717UL",
          "currency": "USD",
          "id": "7TQmC858WXOdFYz4"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "11.99",
      "reference_order": "#PF7130110check",
      "shipping_fee": "5.99",
      "callback_url": "",
      "shipping": {
        "id": "RpbHk0w1uMUEarMI",
        "name": "David Thomas",
        "email": "olivia@thobox.vn",
        "phone": "4.48E+11",
        "gift": false,
        "address": {
          "line1": "6 Yr Ysfa",
          "line2": "Maesteg",
          "city": "Maesteg",
          "state": "WLS",
          "postal_code": "CF34 9AG",
          "country": "GB",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3799358",
      "created_date": "20240715T064442Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "11.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "5.99",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/07/15/48d9c907aa70ab1ca72d7ef60f0e3f23.png",
          "price": "6.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/07/15/b8ac8e852d084e4bbecd44302a55a9bb.jpg",
          "base_short_code": "EUG64000",
          "currency": "USD",
          "id": "Nn5wldv1UOHbm9l7"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "11.99",
      "reference_order": "#PF7130111check",
      "shipping_fee": "5.99",
      "callback_url": "",
      "shipping": {
        "id": "66DSuUlYXnWnDGkg",
        "name": "David Thomas",
        "email": "olivia@thobox.vn",
        "phone": "4.48E+11",
        "gift": false,
        "address": {
          "line1": "6 Yr Ysfa",
          "line2": "Maesteg",
          "city": "Maesteg",
          "state": "WLS",
          "postal_code": "CF34 9AG",
          "country": "GB",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3799359",
      "created_date": "20240715T064442Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "11.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "5.99",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/07/15/705f7794c18c015257b06daad2af97bf.png",
          "price": "6.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/07/15/c1ad0a8af14d7dedd557440e3a9e3ad2.jpg",
          "base_short_code": "EUG64000",
          "currency": "USD",
          "id": "ynPg9kPGyDK1bAAB"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "15.24",
      "reference_order": "",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "N8SzqXZxapcrWmiy",
        "name": "Dr. Török Boróka PhD",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AK",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777518",
      "created_date": "20240619T132445Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "15.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/design/2023/10/18/A30558_RGCJGMJ3b8zTwmpNn0Gu3ZrFe_1697621155078.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/mockup/2023/10/18/A30558_PwLtdk8uDSeSKxuVNoKaPtob5_1697621184582.png",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "gWfOQwxRZPoQpRYW"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "28.99",
      "reference_order": "API 118",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "rJbREqIGVM3uVtSy",
        "name": "checkAPIthuan",
        "email": "dominhthuan@gmail.com",
        "phone": "34",
        "gift": false,
        "address": {
          "line1": "1300 Rosa Parks Blvd",
          "line2": "1",
          "city": "1",
          "state": "AL",
          "postal_code": "1",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "20.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777516",
      "created_date": "20240619T132024Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "28.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "20.50",
          "mockup_front_url": "",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "uazlMaHEYQvw3Mqs"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "31.49",
      "reference_order": "AVietcheckprod",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "LxxjEKC0FPnk2Wfr",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "23.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777515",
      "created_date": "20240619T131543Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "31.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "23.00",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "m4oGICWItY90M2SF"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.49",
      "reference_order": "#PF735622f",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "cZB1BzmKzn7efq3H",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "16.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777505",
      "created_date": "20240619T131100Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "L",
          "shipping_fee": "8.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/1c40dd8242e2a435c3ad905d60552195.png",
          "price": "16.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/833b110c04ee838e8232b305e4eb9bf4.jpg",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "BwI52ikkJdLOAsnc"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "14.99",
      "reference_order": "#PF735623f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "cemoOFEzK8nwmLIK",
        "name": "William Mancini",
        "email": "olivia@thobox.vn",
        "phone": "6026717770",
        "gift": false,
        "address": {
          "line1": "7020 W Olive Ave",
          "line2": "Unit 218",
          "city": "Peoria",
          "state": "AZ",
          "postal_code": "85345",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "9.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777513",
      "created_date": "20240619T131100Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "14.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/c142d20d0886a32f7e9523c31932ed7b.png",
          "price": "9.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/7ea43b8e1962f392c181434a628a2c9f.jpg",
          "base_short_code": "USNL3600",
          "currency": "USD",
          "id": "ud4BQ6qhVupPjmAv"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "16.99",
      "reference_order": "#PF735636f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "ibjUSmtrC6vvH6SG",
        "name": "Philip Waisman",
        "email": "olivia@thobox.vn",
        "phone": "8288179337",
        "gift": false,
        "address": {
          "line1": "484 Silver Ridge Rd",
          "line2": "",
          "city": "Mill Spring",
          "state": "NC",
          "postal_code": "28756",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "11.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777508",
      "created_date": "20240619T131059Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "16.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "2XL",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/108a1fc9c8947248573825d30fcf4bce.png",
          "price": "11.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/a50e79e32865c743dd13238579f046e3.jpg",
          "base_short_code": "USNL3600",
          "currency": "USD",
          "id": "LZVKqV3ZLQlR1IWZ"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "14.99",
      "reference_order": "#PF735628f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "Mp80b3LYSpXFeAs2",
        "name": "Dominic Ingolia",
        "email": "olivia@thobox.vn",
        "phone": "3093030178",
        "gift": false,
        "address": {
          "line1": "806 Springfield Road",
          "line2": "",
          "city": "East Peoria",
          "state": "IL",
          "postal_code": "61611",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "9.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777512",
      "created_date": "20240619T131059Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "14.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "M",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/e221af379b5d97671ba019655a599fba.png",
          "price": "9.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/ce11583391653894618936ed504a3897.jpg",
          "base_short_code": "USNL3600",
          "currency": "USD",
          "id": "q1ue7f1qwOEcNuce"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "14.99",
      "reference_order": "#PF735626f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "b5yY46998xqu5SqK",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "9.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777511",
      "created_date": "20240619T131059Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "14.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "L",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/e801ccd7f9a3eccc1ecadb97dfee2b64.png",
          "price": "9.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/14b3eebe11335f429773532a8f228608.jpg",
          "base_short_code": "USNL3600",
          "currency": "USD",
          "id": "1jpzAbbyY5rcGvS5"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "14.99",
      "reference_order": "#PF735629f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "v5PNLWxmL8vUDrAC",
        "name": "Ericka Comas",
        "email": "olivia@thobox.vn",
        "phone": "4074023842",
        "gift": false,
        "address": {
          "line1": "1613 Caribou Hunt Trail",
          "line2": "",
          "city": "Orlando",
          "state": "FL",
          "postal_code": "32824",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "9.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777509",
      "created_date": "20240619T131059Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "14.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "M",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/add879d4e7d8c703b10598da3e2e40b9.png",
          "price": "9.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/94fc486c64be8209c1349880bd65c1c7.jpg",
          "base_short_code": "USNL3600",
          "currency": "USD",
          "id": "pb8BNggOzF2xhgEr"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "12.24",
      "reference_order": "#PF735631f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "zvkkXbT2dJN8uQTj",
        "name": "Janet S Lingo",
        "email": "olivia@thobox.vn",
        "phone": "3014672800",
        "gift": false,
        "address": {
          "line1": "700 7th St Sw",
          "line2": "Apt 118",
          "city": "WASHINGTON",
          "state": "FL",
          "postal_code": "20024",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777506",
      "created_date": "20240619T131057Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "12.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "L",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/bfaf0c5246e7b7bc023eb1c5e6b73c44.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/821747ffe4223c5dab2fe6765cdca044.jpg",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "C6X1blFz7K8GZtCh"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "12.24",
      "reference_order": "#PF735638f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "ErO0cymObBJmnbGI",
        "name": "Nashae Crawford",
        "email": "olivia@thobox.vn",
        "phone": "8608904768",
        "gift": false,
        "address": {
          "line1": "101 Morningside St W",
          "line2": "",
          "city": "HARTFORD",
          "state": "CT",
          "postal_code": "6112",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777510",
      "created_date": "20240619T131057Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "12.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "M",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/8a4a40266f40a5f94a06542af0887cf0.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/e9397d488fb6794954b8904bf12cf765.jpg",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "amsVSWPXy9NDXtLy"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "12.24",
      "reference_order": "#PF735637f",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "QjgxRbcyqtqEQSgk",
        "name": "Daryl Ranegar",
        "email": "olivia@thobox.vn",
        "phone": "7244132340",
        "gift": false,
        "address": {
          "line1": "485 Fayette Street",
          "line2": "",
          "city": "Washington",
          "state": "PA",
          "postal_code": "15301",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "6.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777507",
      "created_date": "20240619T131057Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "12.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "5.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/19/9636d27f3294626dda3187fa2f067fcf.png",
          "price": "6.75",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/19/3c83b9c43c1198672db9a3166f217b52.jpg",
          "base_short_code": "USG5000",
          "currency": "USD",
          "id": "vq4UDEaXLb3n5ghc"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "26.49",
      "reference_order": "thuanthanthiencheck5",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "XYONly06HXfqxanh",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "18.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777504",
      "created_date": "20240619T130921Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "26.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "18.00",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "UaSFxTkIapC1rxYM"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "104.46",
      "reference_order": "thuanthanthiencheck8",
      "shipping_fee": "17.46",
      "callback_url": "",
      "shipping": {
        "id": "sHx6Jbynf7jkiYHR",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94406",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "87.00",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777502",
      "created_date": "20240619T130920Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "104.46",
          "quantity": "4",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "17.46",
          "design_front_url": "",
          "price": "21.75",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "taNYW1i5n7rrPTCx"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "94.72",
      "reference_order": "thuanthanthiencheck7",
      "shipping_fee": "14.47",
      "callback_url": "",
      "shipping": {
        "id": "6qbbyIoC15TNgDVX",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94405",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "80.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777503",
      "created_date": "20240619T130920Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "94.72",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "14.47",
          "design_front_url": "",
          "price": "26.75",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "7WTo3vuwc9OUa1ok"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "94.72",
      "reference_order": "thuanthanthiencheck9",
      "shipping_fee": "14.47",
      "callback_url": "",
      "shipping": {
        "id": "5k2iMADyJZdbCBo8",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94405",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "80.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777497",
      "created_date": "20240619T130542Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "94.72",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "14.47",
          "design_front_url": "",
          "price": "26.75",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "zDvodV1M9Y0zO3r1"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "27.49",
      "reference_order": "",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "UqluR62Nrg7Wb5xt",
        "name": "Dr. Török Boróka PhD",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AK",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "19.00",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3777496",
      "created_date": "20240619T130500Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "27.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "XL",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "19.00",
          "mockup_front_url": "",
          "base_short_code": "USMECC1717",
          "currency": "USD",
          "id": "Okxj0keQm1qJdzuD"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "78.98",
      "reference_order": "",
      "shipping_fee": "11.48",
      "callback_url": "",
      "shipping": {
        "id": "DUiZiZsN2HL2Qowb",
        "name": "thuanne",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AK",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "67.50",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3772063",
      "created_date": "20240614T124709Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "61.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "53.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/mockup/2023/10/27/A30558_cbC3Gui8lLLlD1ch9Q0sc5dqx_1698400288191.jpg",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "tTsVG8xVaLgKij0x"
        },
        {
          "tax_amount": "0.00",
          "amount": "17.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "2.99",
          "design_front_url": "",
          "price": "14.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/mockup/2023/10/18/A30558_PwLtdk8uDSeSKxuVNoKaPtob5_1697621184582.png",
          "base_short_code": "USMEG5000",
          "currency": "USD",
          "id": "ru5DJngdzYPZYqBc"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "78.98",
      "reference_order": "",
      "shipping_fee": "11.48",
      "callback_url": "",
      "shipping": {
        "id": "J46smiUDJz80gmoC",
        "name": "thuanne",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AK",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "67.50",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3772031",
      "created_date": "20240614T124057Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "61.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "53.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/mockup/2023/10/27/A30558_cbC3Gui8lLLlD1ch9Q0sc5dqx_1698400288191.jpg",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "EQu0zmYTKbMvPaOq"
        },
        {
          "tax_amount": "0.00",
          "amount": "17.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "2.99",
          "design_front_url": "",
          "price": "14.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/mockup/2023/10/18/A30558_PwLtdk8uDSeSKxuVNoKaPtob5_1697621184582.png",
          "base_short_code": "USMEG5000",
          "currency": "USD",
          "id": "ZCvYiFnyJRaBd9RH"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "71.97",
      "reference_order": "",
      "shipping_fee": "11.47",
      "callback_url": "",
      "shipping": {
        "id": "BUsETkOwASBE5N4g",
        "name": "Thuanthanthien",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AL",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "60.50",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3771935",
      "created_date": "20240614T120817Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "14.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "9.50",
          "mockup_front_url": "",
          "base_short_code": "USMEG5000",
          "currency": "USD",
          "id": "K7OXgdDyFUUpqvyr"
        },
        {
          "tax_amount": "0.00",
          "amount": "32.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "2.99",
          "design_front_url": "",
          "price": "29.25",
          "mockup_front_url": "",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "IZOBJBw40Fq7zpcD"
        },
        {
          "tax_amount": "0.00",
          "amount": "24.74",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "2.99",
          "design_front_url": "",
          "price": "21.75",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "TFo0r1MercWSXzPK"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "50.47",
      "reference_order": "api_custom_doormat_3",
      "shipping_fee": "11.47",
      "callback_url": "",
      "shipping": {
        "id": "SuyIjxPhcEHHZfat",
        "name": "james bond",
        "email": "abc@gmail.com",
        "phone": "34",
        "gift": false,
        "address": {
          "line1": "1300 Rosa Parks Blvd",
          "line2": "1",
          "city": "1",
          "state": "AL",
          "postal_code": "1",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "39.00",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3771391",
      "created_date": "20240614T063717Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "50.47",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "mockup_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "size_name": "S",
          "shipping_fee": "11.47",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "price": "13.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "base_short_code": "USGG5000L",
          "currency": "USD",
          "id": "hK3DzDajXGrWo9rZ"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "39.00",
      "reference_order": "api_custom_doormat_2",
      "shipping_fee": "0.0",
      "callback_url": "",
      "shipping": {
        "id": "SPLl8IbC0WCgTQg0",
        "name": "james bond",
        "email": "abc@gmail.com",
        "phone": "34",
        "gift": false,
        "address": {
          "line1": "1300 Rosa Parks Blvd",
          "line2": "1",
          "city": "1",
          "state": "",
          "postal_code": "1",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "39.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3771389",
      "created_date": "20240614T063617Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "39.00",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "mockup_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "size_name": "S",
          "shipping_fee": "0.00",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "price": "13.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "base_short_code": "USGG5000L",
          "currency": "USD",
          "id": "LZlvX1p2HoHY6yIV"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "38.00",
      "reference_order": "api_custom_doormat_1",
      "shipping_fee": "0.5",
      "callback_url": "",
      "shipping": {
        "id": "wnfeBTzrrsD0dUp8",
        "name": "james bond",
        "email": "abc@gmail.com",
        "phone": "34",
        "gift": false,
        "address": {
          "line1": "1300 Rosa Parks Blvd",
          "line2": "1",
          "city": "1",
          "state": "",
          "postal_code": "1",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "37.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3771358",
      "created_date": "20240614T061338Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "38.00",
          "quantity": "3",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "mockup_back_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "size_name": "XL",
          "shipping_fee": "0.50",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "price": "12.50",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/14/8d022653effc981d909564d7016b64a1.jpg",
          "base_short_code": "USMG5000BUL",
          "currency": "USD",
          "id": "bmgzMlBmhOMOHS0S"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "40.99",
      "reference_order": "Checkprod3",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "aaN0YGScKkQGY1js",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "35.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770842",
      "created_date": "20240613T131341Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "40.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "35.50",
          "mockup_front_url": "",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "42tV1VBBkpa8SPrf"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "43.49",
      "reference_order": "Checkprod1",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "bBaaXRRLbLqiQbUj",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "38.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770843",
      "created_date": "20240613T131330Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "43.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "38.00",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "sqDa9Ipz2ZEz6bak"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "21.74",
      "reference_order": "Checkprod2",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "Psq1ziYFc54Tm4gU",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "16.25",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770841",
      "created_date": "20240613T131327Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "21.74",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "16.25",
          "mockup_front_url": "",
          "base_short_code": "USMEBC3001",
          "currency": "USD",
          "id": "tbtyZdjwssn8pEDs"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "43.49",
      "reference_order": "Checkprod",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "kUdC6VH7MaSb1RgV",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "38.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770837",
      "created_date": "20240613T130341Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "43.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "38.00",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "MZfUao6kwaW0Jbvc"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "23.99",
      "reference_order": "",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "NLtBJwcWjExWMz57",
        "name": "Dr. Török Boróka PhD",
        "email": "thuandm@leadsgen.com",
        "phone": "",
        "gift": false,
        "address": {
          "line1": "Arpad sor 1",
          "line2": "",
          "city": "Bekescsaba",
          "state": "AK",
          "postal_code": "5600",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "15.50",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770767",
      "created_date": "20240613T123507Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "23.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "15.50",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "M5VMreMjx0htkDdv"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.49",
      "reference_order": "base thuong design sai dinh dang5",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "kzDIKuTHyPOH2vQo",
        "name": "William Mancini",
        "email": "olivia@thobox.vn",
        "phone": "6262010860",
        "gift": false,
        "address": {
          "line1": "7020 W Olive Ave",
          "line2": "Unit 218",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91767",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "16.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770740",
      "created_date": "20240613T123204Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "https://www.dropbox.com/scl/fi/8s22tm8i5nas1n7ygnkzq/1-m-u-ng.EMB?rlkey=f7mhjtf64rbpoty9u7r4nu6wq&st=xhytx0n4&dl=1",
          "price": "16.00",
          "mockup_front_url": "https://www.dropbox.com/scl/fi/8s22tm8i5nas1n7ygnkzq/1-m-u-ng.EMB?rlkey=f7mhjtf64rbpoty9u7r4nu6wq&st=xhytx0n4&dl=1",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "Z92RMqPS1NvkbuSo"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "25.99",
      "reference_order": "checkvung2",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "xEGwqE0jyz3aBos5",
        "name": "William Mancini",
        "email": "olivia@thobox.vn",
        "phone": "6026717770",
        "gift": false,
        "address": {
          "line1": "7020 W Olive Ave",
          "line2": "Unit 218",
          "city": "Peoria",
          "state": "AZ",
          "postal_code": "85345",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "20.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770702",
      "created_date": "20240613T121537Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "25.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "20.50",
          "mockup_front_url": "",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "GRQzhGda3PzgK1Ik"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "28.49",
      "reference_order": "checkvung1",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "5lQ7fTppJHWalHvT",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "23.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770700",
      "created_date": "20240613T121532Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "28.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "23.00",
          "mockup_front_url": "",
          "base_short_code": "USMEG18500",
          "currency": "USD",
          "id": "3JgfvQEmjjc9NMeT"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "45.48",
      "reference_order": "mix base theu va base thuong3",
      "shipping_fee": "13.98",
      "callback_url": "",
      "shipping": {
        "id": "rjGDs8yw4q0VbvYi",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "31.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770508",
      "created_date": "20240613T114220Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "20.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "15.50",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "vUbHNgb4xIwem3Zs"
        },
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/13/1c40dd8242e2a435c3ad905d60552195.png",
          "price": "16.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/13/1c40dd8242e2a435c3ad905d60552195.png",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "0EZ3lBfNn11lzy3Q"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "45.48",
      "reference_order": "mix thuong dung theu sai vung3",
      "shipping_fee": "13.98",
      "callback_url": "",
      "shipping": {
        "id": "IjZzBFQBLsrQNr4J",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "31.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770512",
      "created_date": "20240613T114220Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/13/1c40dd8242e2a435c3ad905d60552195.png",
          "price": "16.00",
          "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/13/1c40dd8242e2a435c3ad905d60552195.png",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "QHT2Gb0S3b0wG7CP"
        },
        {
          "tax_amount": "0.00",
          "amount": "20.99",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "15.50",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "eOriEmvt2Ymw9qGz"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.49",
      "reference_order": "base thuong design base theu3",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "CJubMhhgsZtH15bC",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "16.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770511",
      "created_date": "20240613T114217Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "16.00",
          "mockup_front_url": "",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "jiepbtMbvc4kSM6N"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "27.24",
      "reference_order": "design sai mau 100%s",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "nb8vrlWIbBuChMeL",
        "name": "Tom Celillo",
        "email": "olivia@thobox.vn",
        "phone": "6506461096",
        "gift": false,
        "address": {
          "line1": "2345 Elliott Street",
          "line2": "",
          "city": "San Mateo",
          "state": "CA",
          "postal_code": "94403",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "21.75",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770502",
      "created_date": "20240613T114143Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "27.24",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "21.75",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "MNk84bXbvZx61gug"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "23.49",
      "reference_order": "design chua it mau sais",
      "shipping_fee": "5.49",
      "callback_url": "",
      "shipping": {
        "id": "h8O9JO6KkUjfV85t",
        "name": "William Mancini",
        "email": "olivia@thobox.vn",
        "phone": "6026717770",
        "gift": false,
        "address": {
          "line1": "7020 W Olive Ave",
          "line2": "Unit 218",
          "city": "Peoria",
          "state": "AZ",
          "postal_code": "85345",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "18.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770504",
      "created_date": "20240613T114143Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "23.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "5.49",
          "design_front_url": "",
          "price": "18.00",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "zYv3LYR2ts3HXqlZ"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "19.69",
      "reference_order": "dia chi sais",
      "shipping_fee": "0.0",
      "callback_url": "",
      "shipping": {
        "id": "6MuD3QxtO3OPhzyq",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "HU",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "15.5",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770503",
      "created_date": "20240613T114143Z",
      "items": [
        {
          "tax_amount": "4.19",
          "amount": "19.69",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.27",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "0.00",
          "design_front_url": "",
          "price": "15.50",
          "mockup_front_url": "",
          "base_short_code": "USMEZS9003",
          "currency": "USD",
          "id": "wrB6T98IMgidBmJa"
        }
      ],
      "payment_date": "",
      "status": "draft"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "26.49",
      "reference_order": "shipping method sais",
      "shipping_fee": "10.99",
      "callback_url": "",
      "shipping": {
        "id": "1JDlHbCyhevkwm6r",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "15.50",
      "shipping_method": "express",
      "store_name": "storff",
      "id": "A30558-CT-3770505",
      "created_date": "20240613T114137Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "26.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "10.99",
          "design_front_url": "",
          "price": "15.50",
          "mockup_front_url": "",
          "base_short_code": "USMEG18000",
          "currency": "USD",
          "id": "k9Bm4vpBuT83SD8v"
        }
      ],
      "payment_date": "",
      "status": "queued"
    },
    {
      "store_id": "KBswl2o1xJYh66UO",
      "amount": "24.49",
      "reference_order": "design chua nhieu mau sais",
      "shipping_fee": "8.49",
      "callback_url": "",
      "shipping": {
        "id": "E5lBhQe2qfBEks4U",
        "name": "Upali Karunaratne",
        "email": "olivia@thobox.vn",
        "phone": "6262010859",
        "gift": false,
        "address": {
          "line1": "1566 Waters Avenue",
          "line2": "",
          "city": "Pomona",
          "state": "CA",
          "postal_code": "91766",
          "country": "US",
          "country_name": "",
          "addr_verified": false,
          "addr_verified_note": ""
        }
      },
      "sub_amount": "16.0",
      "shipping_method": "standard",
      "store_name": "storff",
      "id": "A30558-CT-3770506",
      "created_date": "20240613T114137Z",
      "items": [
        {
          "tax_amount": "0.00",
          "amount": "24.49",
          "quantity": "1",
          "catalog_sku": "",
          "tax_rate": "0.00",
          "design_back_url": "",
          "mockup_back_url": "",
          "size_name": "S",
          "shipping_fee": "8.49",
          "design_front_url": "",
          "price": "16.00",
          "mockup_front_url": "",
          "base_short_code": "USG18500",
          "currency": "USD",
          "id": "s5cr3ksUbayrbrNW"
        }
      ],
      "payment_date": "",
      "status": "draft"
    }
  ]
}
GET
Get an order
https://api.burgerprints.com/v2/order/{id}
Get Order Details
Retrieves information about a specific order.

We also note the order status and fulfillment status as shown in the table below.


Request Body
No request body.
Response Body
The response contains detailed information about all order, including the seller, shipping details, items, payment, promotion, shipping labels, and more.
Example Response
View More
json
{
  "id": "A2075-OV-18710",
  "reference_order_id": "api_custom_doormat_1",
  "production_service":"priority",
  "status": "shipped",
  "amount": "26.49",
"shipping_method": "standard",
"callback_url": "",
  "sub_amount": "16.50",
  "shipping_fee": "9.99",
 "shipping": {
        "id": "mXlnNvxJ0bMAATOk",
        "name": "Dung",
        "email": "nonononoo@gmail.com",
        "phone": "0321123321",
        "gift": false,
        "address": {
            "line1": "Van Quan",
            "line2": "",
            "city": "Ha Noi",
            "state": "AK",
            "postal_code": "10000",
            "country": "",
            "country_name": "United States",
            "addr_verified": false,
            "addr_verified_note": ""
        }
    },
  "items": [
    {
     "tax_amount": "0",
     "amount": "20", 
     "catalog_sku": " IPXR",
      "tax_rate": "0",
      "quantity": "3",
      "size_name": "",
     "shipping_fee": "13.5",
     "price": "6.5",
      "base_short_code": "CABT",
      "currency": "USD",
     "id": "ztcbIYPxv1ZW8yJe",
      "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/isp/2021/02/23/A2360_store_50xfdwf7ulm80.png",
      "design_back_url": "",
      "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/isp/2021/02/23/A2360_store_50xfdwf7ulm80.png",
      "mockup_back_url": " 
       },
    {
      "tax_amount": "0",
     "amount": "20", 
     "catalog_sku": " IPXR",
      "tax_rate": "0",
      "quantity": "3",
      "size_name": "",
     "shipping_fee": "13.5",
     "price": "6.5",
      "base_short_code": "CABT",
      "currency": "USD",
     "id": "ztcbIYPxv1ZW8yJo",
      "design_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/isp/2021/02/23/A2360_store_50xfdwf7ulm80.png",
      "design_back_url": "",
      "mockup_front_url": "https://d1ud88wu9m1k4s.cloudfront.net/isp/2021/02/23/A2360_store_50xfdwf7ulm80.png",
      "mockup_back_url": ""
        }
  ],
  "trackings": [
    {
      "BGP-2020-1369": {
        "carrier": "DHL",
      "created_date": "20221118T015015Z",
        "code": "WD39SGK8GC8ZZ6D0",
        "url": "https://webtrack.dhlglobalmail.com/?trackingnumber=WD39SGK8GC8ZZ6D0"
      }
    },
    {
      "BGP-2020-1370": {
        "carrier": "EMS",
       "created_date": "20221118T015015Z",
        "code": "7TH4XMOSDAJC7YA1",
        "url": "https://t.17track.net/en#nums=7TH4XMOSDAJC7YA1"
      }
    }
  ]
}
HEADERS
api-key
e443f8af-eca2-4a73-8ab2-b287298c3a64

Example Request
success
View More
python
import requests

url = "https://api.burgerprints.com/v2/order/A33378-CT-3744436"

payload={}
headers = {
  'api-key': 'e443f8af-eca2-4a73-8ab2-b287298c3a64'
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
200 OK
Example Response
Body
Headers (13)
View More
json
{
  "code": 200,
  "message": "OK",
  "data": {
    "quote": null,
    "buyer": null,
    "seller": {
      "amount": "7.25",
      "shipping_fee": "0.5",
      "discount_amount": "0.00",
      "clone_price": "0.00",
      "tax_amount": "0.00",
      "payment_processing_fee": "0",
      "payment_info": null,
      "promotion_code": null
    },
    "fulfillment": "Unfulfilled",
    "state": "queued",
    "source": "custom.label",
    "currency": "USD",
    "note": null,
    "store_id": "is9g2RZIMk4dM8Ko",
    "channel": "api",
    "reference_id": "import_0306_1",
    "shipping_method": "standard",
    "shipping": {
      "id": "b6YwNRwLJolsvWk7",
      "email": null,
      "name": null,
      "phone": null,
      "address": {
        "line1": null,
        "line2": null,
        "city": null,
        "state": null,
        "postal_code": null,
        "country": null,
        "country_name": null
      }
    },
    "extra_fee": "0",
    "items": [
      {
        "confirmed": true,
        "id": "SohJLi4JAYk55Pai",
        "name": "Unisex T-shirt | Gildan 5000 (US Label) - Black - S",
        "product_id": "A33378-85812848c41746f3952e3881ca8fe96f",
        "product_type_id": null,
        "variant_id": null,
        "short_code": "USMG5000UL",
        "color_value": "#25282A",
        "color_id": "n4G8MnSzfSmkMyxr",
        "color_name": "Black",
        "size_id": "2JmSZ4DS0C8DrrpV",
        "size_name": "S",
        "quantity": 1,
        "custom_data": "",
        "type": "custom",
        "unit_amount": null,
        "is_clone_design": false,
        "barcode": null,
        "notes": null,
        "designs": [
          {
            "id": "a63c87869e9e46f599b988417076b311",
            "type": "front",
            "src": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/design/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png",
            "calculate_clone_price": true,
            "resolution": "4200x4800",
            "num_stitches": null,
            "colors_code": null,
            "file_size": null,
            "file_name": null
          }
        ],
        "mockups": [
          {
            "id": "",
            "type": "front",
            "src": "https://d1ud88wu9m1k4s.cloudfront.net/fulfill/mockup/2024/06/03/d94aeb361c70821e0331500fc3cc0353.png",
            "calculate_clone_price": true,
            "resolution": null,
            "num_stitches": null,
            "colors_code": null,
            "file_size": null,
            "file_name": null
          }
        ],
        "location": "Bj3ckBDW20wQjith",
        "sku": "USMG5000UL-Black-S",
        "ref_id": null,
        "position": 0,
        "sku_label": null,
        "mockup_api": "2d",
        "additional_designs": null,
        "amount": "7.25",
        "sub_amount": "6.75",
        "price": "6.75",
        "base_cost": "6.75",
        "clone_price": "0.00",
        "currency": "USD",
        "fulfillment_cost": null,
        "shipping_fee": "0.50",
        "tax_rate": "0.00",
        "tax_amount": "0.00",
        "payment_processing_fee": null,
        "shipping_method": "standard",
        "state": "approved",
        "shipping_method_allowed": null,
        "discount_amount": null,
        "tracking_codes": null,
        "trackings": [],
        "buyer_tax": null,
        "buyer_shipping_fee": null,
        "buyer_amount": null,
        "promotion_amount": null,
        "promotion_code": null,
        "promotion_code_amount": null,
        "promotion_auto_id": null,
        "promotion_auto_amount": null,
        "is_personalize": false,
        "quantity_buyer": 1
      }
    ],
    "payment_type": null,
    "ioss_number": null,
    "promotion_code": null,
    "already_applied_auto": false,
    "promotion_auto_id": null,
    "shipping_labels": [
      {
        "name": "A26200_kUKgep0bPAt9Y3mIZNCqtzToS_1717378431693.pdf",
        "url": "https://d1ud88wu9m1k4s.cloudfront.net/home/ec2-user/pspjob/temp/dropship_import_files_download/2024/06/02/A33378/1717383298556_A26200_kUKgep0bPAt9Y3mIZNCqtzToS_1717378431693.pdf"
      }
    ],
    "estimate_promotion": true,
    "shipping_method_buyer": null,
    "custom_label": {
      "tracking_code": "420953569405511109483606511623",
      "tracking_url": null,
      "provider": null,
      "shipping_labels": [
        {
          "name": "A26200_kUKgep0bPAt9Y3mIZNCqtzToS_1717378431693.pdf",
          "url": "https://d1ud88wu9m1k4s.cloudfront.net/home/ec2-user/pspjob/temp/dropship_import_files_download/2024/06/02/A33378/1717383298556_A26200_kUKgep0bPAt9Y3mIZNCqtzToS_1717378431693.pdf"
        }
      ]
    },
    "id": "A33378-CT-3744436",
    "store_name": null,
    "payment_state": "Unpaid",
    "fulfill_state": "Unfulfilled",
    "tracking_codes": null,
    "trackings": [],
    "callback_url": null,
    "domain": null,
    "create_date": "20240602T215459Z",
    "update_date": "20240602T215459Z",
    "order_date": null,
    "user_id": "A33378",
    "total_item": 1,
    "traffic_source": null,
    "shipping_method_allowed": [
      "standard"
    ],
    "all_shipping_method": [
      "standard"
    ],
    "shipping_methods": [
      {
        "id": "standard",
        "name": "Standard",
        "desc": "2-9 business days delivery"
      }
    ],
    "require_refund": false,
    "promotion_amount": "0.00",
    "promotion_message": null,
    "is_promotion_code_valid": false,
    "fulfill_promotion_metadata": null,
    "confirmed_to_fulfill": true,
    "is_personalize": false,
    "is_ticket": true
  }
}
Beta
0 / 0
used queries
1