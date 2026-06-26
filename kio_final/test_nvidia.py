from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NVIDIA_API_KEY"),
    base_url="https://integrate.api.nvidia.com/v1",
    timeout=60
)

print("Sending request...")

response = client.chat.completions.create(
    model="meta/llama-3.1-8b-instruct",
    messages=[
        {
            "role": "user",
            "content": "hi"
        }
    ],
    max_tokens=20,
    temperature=0
)

print("Received response")
print(response.choices[0].message.content)