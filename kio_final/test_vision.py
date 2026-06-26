from dotenv import load_dotenv
from openai import OpenAI
import base64
import os
import time

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NVIDIA_API_KEY"),
    base_url=os.getenv("NVIDIA_BASE_URL"),
    timeout=120
)

IMAGE_PATH = "test.png"  # replace

with open(IMAGE_PATH, "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

start = time.time()

response = client.chat.completions.create(
    model="qwen/qwen3.5-397b-a17b",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe this image in detail."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}"
                    }
                }
            ]
        }
    ],
    max_tokens=1000
)

print(f"TIME: {round(time.time()-start,2)}s")
print(response.choices[0].message.content)