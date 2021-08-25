import toml

class TomlError(Exception):
    pass

# Read configuration file
def load_config(filename):
  config = toml.load(filename)
  # Check the necessary fields are provided in the toml
  if  config.get('contracts') is None or config['contracts'].get('pricefeeds') is None:
    raise TomlError("Please specify ERC2362PriceFeed addresses as \n[contracts]\npricefeed=[\"0xaaaa\", ...]\n")
  elif  config.get('account') is None or config['account'].get('address') is None:
    raise TomlError("Please specify account as \n[account]\naddress=0xaaaa")
  elif  config.get('network') is None or config['network'].get('provider') is None:
    raise TomlError("Please specify account as \n[network]\nprovider=127.0.0.1:8545")
  else:
    return config
