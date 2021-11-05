import toml

class TomlError(Exception):
    pass

# Read configuration file
def load_config(filename):
  config = toml.load(filename)  
  # Check the necessary fields are provided in the toml
  if  config.get('pricefeeds') is None or len(config['pricefeeds']) == 0:
    raise TomlError("Please specify at least one pricefeed underneath [pricefeeds] as\n[pricefeeds]\n  [pricefeeds.giveitananme]\n  contract_address = \"0x...\"\n  deviation_threshold_percentage = 1.5\n")
  elif  config.get('account') is None or config['account'].get('address') is None:
    raise TomlError("Please specify account as \n[account]\naddress=0xaaaa")
  elif  config.get('network') is None or config['network'].get('provider') is None:
    raise TomlError("Please specify account as \n[network]\nprovider=127.0.0.1:8545")
  else:
    return config
