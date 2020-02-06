#!/usr/bin/env python3
import json
import socket
import sys
import time
from web3.auto import w3
from contract import pricefeed, wbi
from config import config


# Post a data request to the post_dr method of the WBI contract
def handle_requestUpdate():
    # set pre-funded account as sender
    account_addr = config["account"]["address"]

    # Check that the accout has enough balance
    balance = w3.eth.getBalance(account_addr)
    if balance == 0:
        raise Exception("Account does not have any funds")

    print(f"Got {balance} wei")


    dr_id = pricefeed.functions.requestUpdate().transact(
        {"from": account_addr, "gas": 310000, "value": 310000000000000})
    post_tx_hash = bytes(dr_id)
    w3.eth.waitForTransactionReceipt(dr_id)
    requestId = pricefeed.functions.lastRequestId().call()

    print(
        f"Data request posted successfully! Ethereum transaction hash:\n{dr_id.hex()}"
    )
    return requestId

def handle_read_data_request():
    # We got a PostDataRequest event!
    print(f"Got data complete request")

     # set pre-funded account as sender
    account_addr = config["account"]["address"]

    # Check that the accout has enough balance
    balance = w3.eth.getBalance(account_addr)
    if balance == 0:
        raise Exception("Account does not have any funds")

    print(f"Got {balance} wei")
    read_id = pricefeed.functions.completeUpdate().transact(
        {"from": account_addr, "gas": 310000})
    post_tx_hash = bytes(read_id)
    w3.eth.waitForTransactionReceipt(read_id)


    btc_price = pricefeed.functions.bitcoinPrice().call()

    print(f"Completed price update. Latest bitcoin price is {btc_price}")


def log_loop(fromBlock, poll_interval):
    print("Waiting for PostDataRequest events...")
    currentId = handle_requestUpdate()
    print(currentId)
    post_result_filter = wbi.events.PostedResult().createFilter(
        fromBlock=fromBlock,
        argument_filters={'_id':currentId}
    )
    while True:
        for event in post_result_filter.get_new_entries():
            handle_read_data_request()
            print("Waiting for PostDataRequest events...")
            currentId = handle_requestUpdate()
            post_result_filter = wbi.events.PostedResult().createFilter(
              fromBlock=fromBlock,
              argument_filters={'_id':currentId}
            )
            ## Only handle first event
            #return
        time.sleep(poll_interval)


def main():
    current_block = w3.eth.blockNumber
    print(f"Current block: {current_block}")
    # Only listen to new events
    fromBlock = current_block
    ## Listen to all events
    #fromBlock = 0
    
    poll_interval = 60  # seconds
    log_loop(current_block, poll_interval)


if __name__ == '__main__':
    main()
