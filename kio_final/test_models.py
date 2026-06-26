from dotenv import load_dotenv
from openai import OpenAI
import os
import time

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NVIDIA_API_KEY"),
    base_url=os.getenv("NVIDIA_BASE_URL"),
    timeout=60
)

MODELS = [
    "meta/llama-4-maverick-17b-128e-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "moonshotai/kimi-k2.6",
    "qwen/qwen3.5-397b-a17b",
    "openai/gpt-oss-120b",
    "minimaxai/minimax-m3",
]

TESTS = {

    "LATENCY": """
Reply with exactly:
OK
""",

    "BROWSER_AGENT": """
User wants:

1. Open Amazon
2. Search Logitech MX Master 3S
3. Filter Prime only
4. Open first result
5. Add to cart

Return the browser execution plan.
""",

    "DEBUGGING": """
Debug this error:

AttributeError: 'NoneType' object has no attribute 'get'

Provide:
1. Root cause
2. Fix
3. Corrected code
""",

    "KIO_ARCHITECTURE": """
Design an architecture for KIO.

Requirements:
- Browser automation
- MCP integration
- Episodic memory
- Tool routing
- Sandboxed execution
- Failure recovery

Keep it concise.
""",

    "PLANNING": """
Create a complete implementation plan for:

Adding browser automation to KIO.

Include:
- Components
- Order of implementation
- Risks
- Testing strategy
""",

    "TOOL_CALLING": """
Available tools:

browser.open(url)
browser.click(selector)
browser.type(selector,text)

User:
Search Google for NVIDIA and open first result.

Return ONLY the tool calls.
""",

    "MEMORY_REASONING": """
Conversation:

User:
My dog's name is Bruno.

User:
I moved to Mumbai.

User:
What is my dog's name?

Answer only.
"""
}


def run_test(model_name, test_name, prompt):
    print("\n" + "=" * 100)
    print(f"MODEL: {model_name}")
    print(f"TEST : {test_name}")
    print("=" * 100)

    try:
        start = time.time()

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=800
        )

        elapsed = round(time.time() - start, 2)

        print(f"\nTIME: {elapsed}s")
        print("-" * 100)

        output = response.choices[0].message.content

        if output:
            print(output[:2000])
        else:
            print("[EMPTY RESPONSE]")

    except Exception as e:
        print(f"\nFAILED: {e}")


print("\n")
print("#" * 100)
print("KIO MODEL BENCHMARK")
print("#" * 100)

for test_name, prompt in TESTS.items():

    print("\n\n")
    print("#" * 100)
    print(f"RUNNING TEST: {test_name}")
    print("#" * 100)

    for model in MODELS:
        run_test(model, test_name, prompt)

print("\n")
print("#" * 100)
print("BENCHMARK COMPLETE")
print("#" * 100)