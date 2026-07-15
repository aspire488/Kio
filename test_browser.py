import os, sys
sys.path.insert(0, '.')
os.environ['KIO_TEST_MODE']='0'
from mini_kio.core.browser_operator import open_url, browser_goto
print('open_url result:', open_url('https://example.com'))
print('browser_goto result:', browser_goto('https://example.com'))
