from dotenv import load_dotenv
import os

load_dotenv()

print(os.getenv("NVIDIA_API_KEY") is not None)
print(os.getenv("NVIDIA_BASE_URL"))
print(os.getenv("NVIDIA_PRIMARY_MODEL"))