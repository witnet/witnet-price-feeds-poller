import json
import toml

class TomlError(Exception):
    pass

def load_version():
  package = json.load(open("package.json"))
  return package.get("name") + " v" + package.get("version")

# Load price feeds configuration parameters from file
def load_price_feeds_config(filename, network_name):
  config = json.load(open(filename))
  chain_name = network_name.split('.')[0]
  return config.get("chains").get(chain_name).get("networks").get(network_name)
