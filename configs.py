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

# Load network configuration file
def load_network_config(filename):
  config = toml.load(filename)  
  # Check the necessary fields are provided in the toml
  if  config.get('network') is None or config['network'].get('name') is None:
    raise TomlError("Please specify network name as \n[network]\nname=\"ethereum.mainnet\"")
  elif  config.get('network') is None or config['network'].get('from') is None:
    raise TomlError("Please specify master address as \n[network]\nfrom=0xaaaa")
  elif  config.get('network') is None or config['network'].get('provider') is None:
    raise TomlError("Please specify network provider as \n[network]\nprovider=127.0.0.1:8545")
  else:
    return config
