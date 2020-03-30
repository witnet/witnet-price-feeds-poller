import json

# Return the wbi contract, given a Ethereum address from "config.toml"
def wrb(w3, config_file):
  contract_address = config_file["contract"]["wrb"]
  # ABI generated using
  # https://remix.ethereum.org
  with open("wrb_abi.json") as json_file:
    contract_abi = json.load(json_file)
    contract = w3.eth.contract(contract_address, abi=contract_abi)
    return contract

# Return the pricefeed contract, given a Ethereum address from "config.toml"
def pricefeed(w3, config_file):
  contract_address = config_file["contract"]["pricefeed"]
    # ABI generated using
    # https://remix.ethereum.org
  with open("pricefeed_abi.json") as json_file:
    contract_abi = json.load(json_file)
    contract = w3.eth.contract(contract_address, abi=contract_abi)
    return contract

