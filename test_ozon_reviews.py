import asyncio
import os
import json
from dotenv import load_dotenv
from app.adapters.channels.ozon.client import OzonClient

async def main():
    load_dotenv()
    client = OzonClient(client_id=os.getenv("OZON_CLIENT_ID"), api_key=os.getenv("OZON_API_KEY"))
    
    print("=== Testing /v1/review/list ===")
    payload = {
        "with_interaction_status": [
            "ALL"
        ],
        "limit": 20,
        "sort_dir": "DESC"
    }
    resp = await client._make_request("POST", "/v1/review/list", json_data=payload)
    if resp:
        print(f"Success, found keys: {resp.keys()}")
        if "reviews" in resp:
             print(f"Found {len(resp['reviews'])} reviews.")
             if resp['reviews']:
                 print(f"Sample review: {json.dumps(resp['reviews'][0], indent=2, ensure_ascii=False)}")
    
    print("=== Testing /v1/review/list with NEW status ===")
    payload3 = {
        "with_interaction_status": [
            "UNVIEWED"
        ],
        "limit": 20,
        "sort_dir": "DESC"
    }
    resp3 = await client._make_request("POST", "/v1/review/list", json_data=payload3)
    if resp3 and "reviews" in resp3:
         print(f"Success with UNVIEWED. Found {len(resp3['reviews'])}")

    print("\n=== Testing /v1/review/message/create ===")
    if resp and "reviews" in resp and resp["reviews"]:
        review_id = resp["reviews"][0]["id"]
        # Try sending an empty string to see validation
        payload5 = {
            "review_id": review_id,
            "text": "test"
        }
        resp5 = await client._make_request("POST", "/v1/review/message/create", json_data=payload5)
        print(f"Response: {resp5}")
        
    print("\n=== Testing /v1/review/comment/create ===")
    if resp and "reviews" in resp and resp["reviews"]:
        review_id = resp["reviews"][0]["id"]
        # Try sending an empty string to see validation
        payload6 = {
            "review_id": review_id,
            "text": "test"
        }
        resp6 = await client._make_request("POST", "/v1/review/comment/create", json_data=payload6)
        print(f"Response: {resp6}")
    
if __name__ == "__main__":
    asyncio.run(main())
