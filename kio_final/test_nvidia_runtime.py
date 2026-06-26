import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("NVIDIA_API_KEY")
BASE_URL = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1"
)

PRIMARY = os.getenv(
    "NVIDIA_PRIMARY_MODEL",
    "meta/llama-4-maverick-17b-128e-instruct"
)

CODE = os.getenv(
    "NVIDIA_CODE_MODEL",
    "openai/gpt-oss-120b"
)

VISION = os.getenv(
    "NVIDIA_VISION_MODEL",
    "qwen/qwen3.5-397b-a17b"
)

print("=" * 80)
print("NVIDIA VALIDATION")
print("=" * 80)

print("API KEY FOUND:", bool(API_KEY))
print("BASE URL:", BASE_URL)
print("PRIMARY:", PRIMARY)
print("CODE:", CODE)
print("VISION:", VISION)
print()

if not API_KEY:
    raise RuntimeError("NVIDIA_API_KEY not found")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


def run_test(name: str, model: str, prompt: str, max_tokens: int = 200):
    print("=" * 80)
    print(f"TEST: {name}")
    print(f"MODEL: {model}")
    print()

    try:
        start = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )

        elapsed = time.time() - start

        print(f"LATENCY: {elapsed:.2f}s")
        print()
        print(response.choices[0].message.content)
        print()

    except Exception as e:
        print("FAILED")
        print(repr(e))
        print()


# ------------------------------------------------------------------
# MODEL CATALOG CHECK
# ------------------------------------------------------------------

print("=" * 80)
print("MODEL CATALOG")
print("=" * 80)

models = client.models.list()
model_ids = {m.id for m in models.data}

print(f"TOTAL MODELS: {len(model_ids)}")
print()

for model in [PRIMARY, CODE, VISION]:
    print(
        f"{model}: {'FOUND' if model in model_ids else 'MISSING'}"
    )

print()

# ------------------------------------------------------------------
# MAVERICK
# ------------------------------------------------------------------

run_test(
    "MAVERICK CHAT",
    PRIMARY,
    "Who directed Interstellar? Answer in two sentences."
)

run_test(
    "MAVERICK PLANNING",
    PRIMARY,
    """
Create a 5-step plan for implementing browser ownership tracking.

Requirements:
- open
- close
- switch
- focus
- close it
"""
)

# ------------------------------------------------------------------
# GPT-OSS
# ------------------------------------------------------------------

run_test(
    "GPT-OSS DEBUGGING",
    CODE,
    """
Python:

x = [1,2,3]
print(x[5])

Explain the bug and fix it.
"""
)

run_test(
    "GPT-OSS ARCHITECTURE",
    CODE,
    """
Design a target ownership system for:

- browser tabs
- desktop apps

Requirements:

close it
focus it
switch to it

must work reliably.
"""
)

# ------------------------------------------------------------------
# QWEN
# ------------------------------------------------------------------

run_test(
    "QWEN CHECK",
    VISION,
    "Reply with exactly: QWEN_OK",
    max_tokens=20
)

print("=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "user",
            "content": """
Design a browser ownership system.

Requirements:

open github
open youtube
switch to youtube
close github
close it

Need deterministic ownership tracking.
"""
        }
    ],
    max_tokens=800,
)

print(repr(response.choices[0].message.content))