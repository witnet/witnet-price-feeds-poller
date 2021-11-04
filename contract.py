import json

# Return the wbi contract, given an address
def wrb(w3, addr):
  with open("abis/WitnetRequestBoard.json") as json_file:
    wrb_abi = json.load(json_file)
    contract = w3.eth.contract(addr, abi=wrb_abi)
    return contract

# Return the pricefeed contracts, attached to the addresses in "config.toml"
def pf_contracts(w3, config_file):
  addresses = config_file["pricefeeds"]["addresses"]
  with open("abis/ERC2362PriceFeed.json") as json_file:
    pricefeed_abi = json.load(json_file)
    return [w3.eth.contract(address, abi=pricefeed_abi) for address in addresses]

# Return the pricefeed deviation thresholds for each pricefeed:
def pf_thresholds(config_file):
  if config_file["pricefeeds"].get("thresholds") is not None:
    thresholds = config_file["pricefeeds"]["thresholds"]
    return [ threshold for threshold in thresholds ]
  else:
    return []
