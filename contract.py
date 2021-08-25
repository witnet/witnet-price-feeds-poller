import json

# Return the wbi contract, given an address
def wrb(w3, addr):
  with open("abis/WitnetRequestBoard.json") as json_file:
    wrb_abi = json.load(json_file)
    contract = w3.eth.contract(addr, abi=wrb_abi)
    return contract

# Return the pricefeed contracts, attached to the addresses in "config.toml"
def pricefeed(w3, config_file):
  contract_addresses = config_file["contracts"]["pricefeeds"]
  with open("abis/ERC2362PriceFeed.json") as json_file:
    pricefeed_abi = json.load(json_file)
    return [w3.eth.contract(address, abi=pricefeed_abi) for address in contract_addresses]
