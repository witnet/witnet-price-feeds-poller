import toml

class TomlError(Exception):
    pass

# Read configuration file
def load_config(filename):
  config = toml.load(filename)
  # Check the necessary fields are provided in the toml
  if  config.get('contract') is None or config['contract'].get('pricefeed') is None or config['contract'].get('wbi') is None:
    raise TomlError("Please specify pricefeed and wbi as \n[contract]\npricefeed=0xaaaa\nwbi=0xbbbb")
  elif  config.get('account') is None or config['account'].get('address') is None:
    raise TomlError("Please specify account as \n[account]\naddress=0xaaaa")
  elif  config.get('network') is None or config['network'].get('provider') is None:
    raise TomlError("Please specify account as \n[network]\nprovider=127.0.0.1:8545")
  else:
    return config
