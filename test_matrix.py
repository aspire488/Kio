from kio_final.mini_kio.core.app_operator import launch_app, close_app
import time

apps_to_test = ['calc', 'notepad', 'cmd']

for app in apps_to_test:
    print(f'--- Testing {app} ---')
    res = launch_app(app)
    print(res)
    if res.get('success'):
        time.sleep(2)
        print(close_app(app, res.get('pid')))
    print('\n')
