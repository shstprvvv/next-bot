import asyncio
from app.config import load_config
from app.adapters.channels.wildberries.client import WBClient
from dotenv import load_dotenv
import os

async def main():
    load_dotenv()
    api_key = os.getenv("WB_API_KEY")
    if not api_key:
        print("No API key")
        return
        
    client = WBClient(api_key=api_key)
    # Get without dateFrom
    feedbacks = await client.get_unanswered_feedbacks(take=5)
    print(f"Total feedbacks fetched: {len(feedbacks)}")
    if feedbacks:
        for fb in feedbacks:
            print("---")
            print(f"ID: {fb.get('id')}")
            print(f"Text: {fb.get('text')}")
            print(f"Valuation: {fb.get('productValuation')}")
            print(f"Answer: {fb.get('answer')}")
    
    await client.aclose()

asyncio.run(main())
