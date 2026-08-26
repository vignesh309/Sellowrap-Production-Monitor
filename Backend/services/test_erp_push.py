import requests
import json

# 1. The ERP API Endpoint
url = "https://f1657.finsys.software:1516/fin-base/om_json_production.aspx"

# 2. Your exact JSON payload
payload = [
    {
        "shop_floor": "SW0103",
        "shift": "Shift A",
        "prd_start_time": "2026-08-25T16:00:00.000Z",
        "prd_end_time": "2026-08-25T17:00:00.000Z",
        "Section": "61",
        "data": [
            {
                "Mould_id": "10297970",
                "Line_superv": "Nandhakumar",
                "no_help": "001",
                "no_opr": "001",
                "machine_id": "IM06-80T-1",
                "part_code": {
                    "10297970-MOULDING": {
                        "Job_no": "-",
                        "Job_dt": "25/08/2026",
                        "ok_qty": 366,
                        "rej_qty": 0,
                        "Lumps": 0,
                        "uid": "2026-08-25_A_IM06-80T-1_10297970_10297970_1600-1700",
                        "rej_category": {}
                    }
                },
                "type": "simple",
                "TOT_DT": 0.0,
                "dt_category": {}
            }
        ]
    }
]

# 3. Set the headers (Telling their server exactly what type of data we are sending)
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json" 
}

print(f"🚀 Pushing data to {url}...\n")

try:
    # 4. Push the data using an HTTP POST request
    # NOTE: We use `json=payload` instead of `data=payload` so the requests library 
    # automatically formats it correctly into a JSON string for us.
    response = requests.post(url, json=payload, headers=headers, timeout=15)

    # 5. Read the Response!
    print(f"Status Code: {response.status_code}")
    
    # Check if the push was mathematically successful (HTTP 200 OK or 201 Created)
    if response.status_code in [200, 201]:
        print("✅ Success! The ERP server accepted the request.")
    else:
        print(f"⚠️ Warning: The server returned an error code.")

    # 6. Print the exact message the ERP server sent back
    print("\n--- ERP Server Response ---")
    try:
        # Try to parse their response as JSON to make it easy to read
        response_data = response.json()
        print(json.dumps(response_data, indent=4))
    except ValueError:
        # If they reply with plain text or HTML instead of JSON, just print the raw text
        print(response.text)

except requests.exceptions.RequestException as e:
    # This catches network errors, timeouts, or DNS issues
    print(f"❌ Failed to connect to the ERP server: {e}")