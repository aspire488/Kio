import sys, os, logging
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
from dotenv import load_dotenv
load_dotenv()
from kio_bot import run_bot
run_bot()
