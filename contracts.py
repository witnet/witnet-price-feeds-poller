import json

# Return the Witnet Price Registry contract, given an address
def wpr_contract(w3, addr):
  with open("abis/WitnetPriceRouter.json") as json_file:
    wpr_abi = json.load(json_file)
    contract = w3.eth.contract(addr, abi=wpr_abi)
    return contract

# Return the pricefeed contracts, attached to the addresses in "config.toml"
def wpf_contract(w3, addr):
  with open("abis/WitnetPriceFeed.json") as json_file:
    wpf_abi = json.load(json_file)  
    contract = w3.eth.contract(addr, abi=wpf_abi)
  return contract
