import sys, os
sys.path.insert(0, '.')
os.chdir(r'C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final')
from mini_kio.core.pipeline import Pipeline

p = Pipeline()

cases = [
    'give me a summary of recent news',
    'give me a summary about climate change',
    'give me an essay about dogs',
    'give me a report on sales',
    'give me a comparison of cats and dogs',
    'give me a poem about rain',
]
for text in cases:
    decision = p.classify(text)
    artifact = decision.metadata.get("artifact", "-")
    print('{:55s} -> intent={:20s} action={:20s} artifact={}'.format(
        repr(text), decision.intent_type.value, decision.action, artifact))
