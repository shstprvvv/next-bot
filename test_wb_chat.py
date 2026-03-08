import asyncio
import httpx
from app.config import load_config
from dotenv import load_dotenv
import os

async def main():
    load_dotenv()
    api_key = os.getenv("WB_API_KEY")
    if not api_key:
        print("No API key")
        return
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Let's get the last few events
    async with httpx.AsyncClient() as client:
        # Without next_token, maybe it gives an error or default
        url = "https://buyer-chat-api.wildberries.ru/api/v1/seller/events"
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            events = data.get("result", {}).get("events", [])
            print(f"Got {len(events)} events")
            if events:
                print("First event:", events[0])
                print("Last event:", events[-1])
                
                # Print unique senders
                senders = set(e.get("sender") for e in events)
                print("Senders:", senders)
                
                event_types = set(e.get("eventType") for e in events)
                print("Event types:", event_types)
        else:
            print("Error:", resp.status_code, resp.text)

asyncio.run(main())
