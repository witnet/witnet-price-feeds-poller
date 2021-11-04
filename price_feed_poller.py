#!/usr/bin/env python3
import argparse
import json
import socket
import sys
import time
import datetime
from web3 import Web3, exceptions
from contract import pricefeed, wrb
from config import load_config

# Post a data request to the post_dr method of the WRB contract
def handle_requestUpdate(
    w3,
    pricefeedcontract,
    wrbcontract,
    account_addr,
    gas,
    gas_price,
    tx_waiting_timeout_secs,
    tx_polling_latency_secs
  ):

    try:
      # Check that the account has enough balance
      balance = w3.eth.getBalance(account_addr)

      if balance == 0:
          raise Exception("Account does not have any funds")
      print(f"Balance: {balance} wei")

      if gas_price is None:
        print(f"Estimating gas price from last blocks...")
        gas_price = w3.eth.generateGasPrice()
      print(f"Gas price: {gas_price}")

      reward = wrbcontract.functions.estimateReward(gas_price).call()
      print(f"Reward: {reward}")

      dr_id = pricefeedcontract.functions.requestUpdate().transact({
        "from": account_addr,
        "gas": gas,
        "gasPrice": gas_price,
        "value": reward
      })

      # Get receipt of the transaction
      print(f"Requesting update on {pricefeedcontract.address} (tx: {dr_id.hex()})...")
      receipt = w3.eth.waitForTransactionReceipt(dr_id, tx_waiting_timeout_secs, tx_polling_latency_secs)

    except exceptions.TimeExhausted:
      print(f"Transaction for requesting update on {pricefeedcontract.address} is taking too long. Retrying in next iteration.")
      return False

    except Exception as ex:
      print(f"Failed when trying to update request on {pricefeedcontract.address}. Retrying in next iteration.")
      print(f"Exception: {ex}")
      return False

    # Check if transaction was succesful
    if receipt['status']:
      print(
        f"Data request for contract {pricefeedcontract.address} posted successfully!"
      )
    else:
      print(
        f"Data request for contract {pricefeedcontract.address} post transaction failed. Retrying in next iteration"
      )
    return receipt['status']

def handle_completeUpdate(
    w3,
    pricefeedcontract,
    account_addr,
    gas,
    gas_price,
    tx_waiting_timeout_secs,
    tx_polling_latency_secs
  ):

    # We got a Read DR request!
    print(f"Got data complete request")

    try:
      # Check that the account has enough balance
      balance = w3.eth.getBalance(account_addr)
      if balance == 0:
        raise Exception("Account does not have any funds")
      print(f"Balance: {balance} wei")

      if gas_price is None:
        print(f"Estimating gas price from last blocks...")
        gas_price = w3.eth.generateGasPrice()
      print(f"Gas price: {gas_price}")

      read_id = pricefeedcontract.functions.completeUpdate().transact({
        "from": account_addr,
        "gas": gas,
        "gasPrice": gas_price
      })

      # Get receipt of the transaction
      print(f"Completing update on {pricefeedcontract.address} (tx: {read_id.hex()})...")
      receipt = w3.eth.waitForTransactionReceipt(read_id, tx_waiting_timeout_secs, tx_polling_latency_secs)

    except exceptions.TimeExhausted:
      print(f"Transaction for completing update on {pricefeedcontract.address} is taking too long. Retrying in next iteration.")
      return False

    except Exception as ex:
      print(f"Failed when trying to complete update on {pricefeedcontract.address}. Retrying in next iteration.")
      print(f"Exception: {ex}")
      return False

    # Check if transaction was succesful
    if receipt['status']:
      try:
        price = pricefeedcontract.functions.lastPrice().call()
        print(f"Completed price update for contract {pricefeedcontract.address}: latest price is {price}.")
      except:
        # At this point we know the transaction ocurred but we could not get the latest state. Retry later.
        log_exception_state(pricefeedcontract.address, "handle complete update")
        return True
    else:
      print(
        f"Read DR result failed. Retrying in next iteration."
      )
    return receipt['status']

def log_exception_state(addr, reason):
  # log the error and wait 1 second before next iteration
  print(f"Error getting the state of contract {addr}: {reason}. Re-trying in next iterations")
  time.sleep(1)

@contextlib.contextmanager
def stdoutIO(stdout=None):
  old = sys.stdout
  if stdout is None:
    stdout = StringIO()
  sys.stdout = stdout
  yield stdout
  sys.stdout = old

def dry_run_request(bytecode):
  cmdline = "npx witnet-toolkit try-data-request --hex "
  cmdline += bytecode.hex()
  cmdline += " | tail -n 2 | head -n 1 | awk -F: '{ print $2 }' | sed 's/ //g' | tr -d \"│\""
  # print(cmdline)
  process = subprocess.Popen(cmdline, stdout=subprocess.PIPE, shell=True)
  process.wait()
  output, error = process.communicate()
  if error is not None:
    raise Exception(error)
  return int(output)

def log_loop(
    w3,
    pricefeeds,
    thresholds,
    account,
    gas,
    gas_price,
    loop_interval_secs,
    tx_waiting_timeout_secs,
    tx_polling_latency_secs,
    min_secs_between_request_updates,
    max_secs_between_request_updates,
  ):

    print("Checking status of contracts...")
    timestamps = [0] * len(pricefeeds)

    while True:
      contracts_information = []
      # Get current Id of the DR
      for feed in pricefeeds:
        try:
          currentId = feed.functions.requestId().call()
          contract_status = feed.functions.pending().call()
          lastPrice = feed.functions.lastPrice().call()
          # TODO: Use ethereum timestamps is not a recommended practice
          # In the future we could use Witnet block number or a database file
          lastResponseItems = feed.functions.lastResponse().call()
          contracts_information.append({
            "feed" : feed,
            "status" : contract_status,
            "currentId" : currentId,
            "lastPrice": lastPrice,
            "lastTimestamp" : lastResponseItems[1]
          })
          print("Latest request Id for contract %s is #%d (pending: %s)" % (feed.address, currentId, contract_status))
        except Exception as ex:
          # Error calling the state of the contract. Wait and re-try
          log_exception_state(feed.address, f"price feed call: {ex}")
          continue

      # Check the state of the contracts
      for element in contracts_information:
        index = contracts_information.index(element)
        try:
          wrbcontract = wrb(w3, feed.functions.witnet().call())
        except Exception as ex:
          # Error when getting the entrypoint to the Witnet Request Board from the pricefeed
          log_exception_state(feed.address, f"witnet() call: {ex}")
          continue

        # Check if the result is ready
        if element["status"]:          
          try:            
            queryStatus = wrbcontract.functions.getQueryStatus(element["currentId"]).call()

          except Exception as ex:
            # Error calling the state of the contract. Wait and re-try
            log_exception_state(wrbcontract.address, f"getQueryStatus({element['currentId']}) call: {ex}")
            continue

          if queryStatus == 2: 
            # The query has been resolved, so complete the update:
            success = handle_completeUpdate(
              w3,
              element["feed"],
              account,
              gas,
              gas_price,
              tx_waiting_timeout_secs,
              tx_polling_latency_secs
            )
            # if completeUpdate was not successfull, it will be called again in next iteration
          else:
            # Result not ready. Wait for following group
            print("Waiting in contract %s for DR Result #%d" % (element["feed"].address, element["currentId"]))

        else:
          if timestamps[index] == 0:
            last_ts = element["lastTimestamp"]
            readable_ts = datetime.datetime.fromtimestamp(last_ts)
            print(f"Price value from contract {element['feed'].address} last updated at {readable_ts.strftime('%Y-%m-%d %H:%M:%S')}")
            timestamps[index] = last_ts

          # Check elapsed time since last request to this feed contract:
          current_ts = int(time.time())
          elapsed_secs = current_ts - timestamps[index]
          if timestamps[index] == 0 or elapsed_secs >= min_secs_between_request_updates:
            last_price = element["lastPrice"]
            if last_price > 0 and len(thresholds) > 0:
              # If threshold is configured, evaluate actual price deviation  
              next_price = dry_run_request(element['feed'].functions.bytecode().call())
              deviation = round(100 * ((next_price - last_price) / last_price), 2)
              if abs(deviation) < thresholds[index] and elapsed_secs < max_secs_between_request_updates:
                # If deviation is below threshold, skip request update until another `min_secs_between_request_updates` secs
                print(f"Price deviation from contract {element['feed'].address} is below threshold ({abs(deviation)}% < {thresholds[index]}%)")
                continue
              else:
                print(f"Next price integer value from contract {element['feed'].address} would rather be {next_price} instead of {last_price}.")
            # Contract waiting for next request to be sent
            success = handle_requestUpdate(
              w3,
              element["feed"],
              wrbcontract,
              account,
              gas,
              gas_price,
              tx_waiting_timeout_secs,
              tx_polling_latency_secs
            )
            if success:
              if timestamps[index] != 0:
                print("Requested new update on contract %s after %d seconds since the last one."
                  % (element["feed"].address, elapsed_secs)
                )
              timestamps[index] = current_ts

      # Loop
      time.sleep(loop_interval_secs)


def main(args):
    # Load the config from the config file:
    config = load_config(args.config_file)
    # Load providers:
    provider = args.provider if args.provider else  config['network']['provider']
    provider_timeout_secs = config['network'].get("provider_timeout_secs", 60)
    # Open web3 provider from the arguments provided:
    w3 = Web3(Web3.HTTPProvider(provider, request_kwargs={'timeout': provider_timeout_secs}))
    # Load configured pricefeed contracts:
    pricefeeds = pf_contracts(w3, config)
    # Load configured pricefeed thresholds if any
    thresholds = pf_thresholds(config)
    if len(thresholds) > 0:
      assert(len(thresholds) == len(pricefeeds))
      print("Deviation thresholds:", thresholds)
    # Get account:
    account = config["account"]["address"]
    # Get minimum secs between update requests (for each given feed contract):
    min_secs_between_request_updates = config["account"].get("min_secs_between_request_updates", 300)
    # Get maximum secs between update requests (for each given feed contract):
    max_secs_between_request_updates = config["account"].get("max_secs_between_request_updates", 3600)
    # Get gas limit, defaults to 4 million units:
    gas = config["network"].get("gas", 4000000)
    # Get gas price, defaults to "estimate_medium":
    gas_price = config["network"].get("gas_price", "estimate_medium")
    # Get HTTP-JSON-RPC waiting timeout (in secs):
    tx_waiting_timeout_secs = config["network"].get("tx_waiting_timeout_secs", 130)
    # Get HTTP-JSON-RPC polling latency timeout (in secs):
    tx_polling_latency_secs = config["network"].get("tx_polling_latency_secs", 13)

    # Try connecting to JSON-RPC provider and get latest block:
    try:
      current_block = w3.eth.blockNumber
      print(f"Connected to {provider}")
    except Exception as ex:
      print(f"Fatal: connection failed to {provider}: {ex}")
      exit(-1)

    print(f"Current block: {current_block}")

    if not isinstance(gas_price, int):
      if gas_price == "estimate_medium" and w3.eth.chainId == 1:
        from web3 import middleware
        from web3.gas_strategies.time_based import medium_gas_price_strategy

        # Transaction mined within 5 minutes
        w3.eth.setGasPriceStrategy(medium_gas_price_strategy)

        # Setup cache because get price is slow (it needs 120 blocks)
        w3.middleware_onion.add(middleware.time_based_cache_middleware)
        w3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
        w3.middleware_onion.add(middleware.simple_cache_middleware)

        gas_price = None
      else:
        if gas_price == "estimate_medium" and w3.eth.chainId != 1:
          print(f"Invalid gas price: {gas_price}. \"estimate_medium\" can only be used for mainnet (current id: {w3.eth.chainId})")
        else:
          print(f"Invalid gas price: {gas_price}. `gas_price` can only be an integer or \"estimate_medium\".")
        exit(1)

    # Call main loop
    log_loop(
      w3,
      pricefeeds,
      thresholds,
      account,
      gas,
      gas_price,
      args.loop_interval_secs,
      tx_waiting_timeout_secs,
      tx_polling_latency_secs,
      min_secs_between_request_updates,
      max_secs_between_request_updates,
    )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Connect to an Ethereum provider.')
    parser.add_argument('--config_file', dest='config_file', action='store', required=True,
                    help='provide the config toml file with the contract and provider details')
    parser.add_argument('--loop_interval_secs', dest='loop_interval_secs', action='store', type=int, required=False, default=30,
                    help='seconds after which the script triggers the state of the smart contract')
    parser.add_argument('--provider', dest='provider', action='store', required=False,
                    help='web3 provider to which the poller should connect. If not provided it reads from config')

    args = parser.parse_args()
    main(args)
