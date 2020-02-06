import json
from web3.auto import w3
from config import config


# Return the wbi contract, given a Ethereum address from "config.toml"
def wbi():
  contract_address = config["contract"]["wbi"]
  # ABI generated using
  # https://remix.ethereum.org
  with open("wbi_abi.json") as json_file:
    contract_abi = json.load(json_file)
    contract = w3.eth.contract(contract_address, abi=contract_abi)
    return contract

def pricefeed():
  contract_address = config["contract"]["pricefeed"]
    # ABI generated using
    # https://remix.ethereum.org
  with open("pricefeed_abi.json") as json_file:
    contract_abi = json.load(json_file)
    contract = w3.eth.contract(contract_address, abi=contract_abi)
    return contract

wbi = wbi()
pricefeed = pricefeed()
