import json
import urllib3

class TomlError(Exception):
    pass

def load_version():
  package = json.load(open("package.json"))
  return package.get("name") + " v" + package.get("version")

# Load price feeds configuration parameters from file
def load_price_feeds_config(path, network_name):
  chain_name = network_name.split('.')[0]
  try:
    if path.startswith("http"):
      http = urllib3.PoolManager(timeout=3.0)
      response = http.request('GET', path)
      config = json.loads(response.data.decode('utf-8'))
    else:
      config = json.load(open(path))
  except Exception as ex:
    return None 
  return config.get("chains").get(chain_name).get("networks").get(network_name)
