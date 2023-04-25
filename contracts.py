import json

# Return the Witnet Price Registry contract, given an address
def feeds_contract(w3, addr):
  with open("abis/WitnetPriceFeeds.json") as json_file:
    feeds_abi = json.load(json_file)
    return w3.eth.contract(addr, abi=feeds_abi)