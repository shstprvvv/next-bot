from openai import AsyncOpenAI
client = AsyncOpenAI(api_key="test")
print("beta attributes:", dir(client.beta))
print("client attributes:", dir(client))
