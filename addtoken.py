import sys
import argparse
from httplib2 import Http
from oauth2client import file, client, tools

def main(acc):
    store = file.Storage(f'tokens/{acc}.json')
    scope = 'https://www.googleapis.com/auth/drive'
    flow = client.flow_from_clientsecrets('credentials.json', scope)
    parser = argparse.ArgumentParser(parents=[tools.argparser])
    parser.add_argument('args', nargs=argparse.REMAINDER)
    flags = parser.parse_args()
    flags.noauth_local_webserver = True
    tools.run_flow(flow, store, flags)

if __name__ == '__main__':
    try: acc = sys.argv[1]
    except: acc = input('vserver : ')
    main(acc)
