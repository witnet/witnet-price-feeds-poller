import json
import urllib3

def load_version():
  package = json.load(open("package.json"))
  return package.get("name") + " v" + package.get("version")

def load_dfe_config(path):
  try:
    if path.startswith("http"):
      http = urllib3.PoolManager(timeout=3.0)
      response = http.request('GET', path)
      config = json.loads(response.data.decode('utf-8'))
    else:
      config = json.load(open(path))
  except Exception as ex:
    print(f"Fatal exception when trying to read triggering conditions from {path}:\n=> {ex}")
    exit(1)
  return config

def get_network_config(config, network_name):
  chain_name = network_name.split('.')[0]
  return config.get("chains").get(chain_name).get("networks").get(network_name)

def get_currency_symbol(config, currency):
  return config.get("currencies").get(currency, "")

def get_price_feed_config(config, network_name, caption, param, default):
  network_config = get_network_config(config, network_name)
  value = network_config['feeds'].get(caption, {}).get(param, None)
  if value is None:
    value = config['conditions'].get(caption, {}).get(param, None)
    if value is None:
      value = config['conditions']['default'].get(param, None)
      if value is None:
        value = default
  return value
