#!/usr/bin/env python3
import argparse
import contextlib
import datetime
import os
import subprocess
import sys
import time

from configs import load_network_config, load_price_feeds_config
from contracts import wpr_contract, wpf_contract
from web3 import Web3, exceptions

# Post a data request to the post_dr method of the WRB contract
def handle_requestUpdate(
    w3,
    csv_filename,
    contract,
    network_symbol,    
    network_from,
    network_gas,
    network_gas_price,
    network_tx_waiting_timeout_secs,
    network_tx_polling_latency_secs
  ):

    try:
      # Check that the account has enough balance
      balance = w3.eth.getBalance(network_from)
      if balance == 0:
          raise Exception("Master account run out of funds")

      if network_gas_price is None:
        print(f"Estimating gas price from last blocks...")
        network_gas_price = w3.eth.generateGasPrice()

      fee = contract.functions.estimateUpdateFee(network_gas_price).call()
      tx = contract.functions.requestUpdate().transact({
        "from": network_from,
        "gas": network_gas,
        "gasPrice": network_gas_price,
        "value": fee
      })
      log_master_balance(csv_filename, network_from, balance, tx.hex())

      # Get receipt of the transaction
      print(f" - Witnet    : {contract.functions.witnet().call()}")
      print(f" - Pricefeed : {contract.address}")
      print(f" - Account   : {network_from}")
      print(f" - Balance   : {round(balance / 10 ** 18, 5)} {network_symbol}")
      print(f" - Paying fee: {round(fee / 10 ** 18, 5)} {network_symbol}")
      print( " - Gas limit :", "{:,}".format(network_gas))
      print( " - Gas price :", "{:,}".format(network_gas_price))
      print(f" = Tx hash   : {tx.hex()}")
      receipt = w3.eth.waitForTransactionReceipt(
        tx,
        network_tx_waiting_timeout_secs,
        network_tx_polling_latency_secs
      )
      print( " = Tx.eff.gas:", "{:,}".format(receipt.get("gasUsed")))
      print( " = Total cost:", round((balance - w3.eth.getBalance(network_from)) / 10 ** 18, 5), network_symbol)

    except exceptions.TimeExhausted:
      print(f" * Transaction is taking too long.")
      return 0

    except Exception as ex:
      print(f" x Transaction rejected: {ex}")
      return 0

    # Check if transaction was succesful
    if receipt['status'] == False:
      print(f" x Transaction reverted!")
      return 0
    else:      
      requestId = contract.functions.latestQueryId().call()
      print(f" < Request id: {requestId}")
      return requestId

def log_master_balance(csv_filename, addr, balance, txhash):
  if csv_filename is not None:
    try:
      with open(csv_filename, "a", encoding="utf-8") as csv_file:
        readable_ts = datetime.datetime.fromtimestamp(int(time.time())).strftime('%Y-%m-%d %H:%M:%S %Z')
        row = f"\"{os.path.splitext(os.path.basename(csv_filename))[0]}\";\"{addr}\";\"{readable_ts}\";\"{balance}\";\"{txhash}\""
        csv_file.write(row + '\n')
    except:
      return

def log_exception_state(addr, reason):
  # log the error and wait 1 second before next iteration
  print(f"Exception while getting state from contract {addr}:\n{reason}")
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
  process = subprocess.Popen(cmdline, stdout=subprocess.PIPE, shell=True)
  process.wait()
  output, error = process.communicate()
  if error is not None:
    raise Exception(error)
  return int(output)

def log_loop(
    w3,
    loop_interval_secs,
    csv_filename,
    pfs_config,
    network_symbol,
    network_from,
    network_gas,
    network_gas_price,
    network_tx_waiting_timeout_secs,
    network_tx_polling_latency_secs,
    network_witnet_resolution_secs    
  ):
    pfs_router = wpr_contract(w3, pfs_config['address'])
    if pfs_router.address is None:
      print("Fatal: no WitnetPriceRouter address")
      exit(1)
    print(f"Using WitnetPriceRouter at {pfs_router.address}\n")
    
    pfs = []    
    for caption in pfs_config['feeds']:
      erc2362id = pfs_router.functions.currencyPairId(caption).call().hex()
      if pfs_router.functions.supportsCurrencyPair(erc2362id).call():
        contract = wpf_contract(w3, pfs_router.functions.getPriceFeed(erc2362id).call())
        deviation = pfs_config['feeds'][caption].get("deviationPercentage", 2.0)
        heartbeat = int(pfs_config['feeds'][caption].get("maxSecsBetweenUpdates", 86400))
        lastPrice = int(contract.functions.lastPrice().call())
        lastTimestamp = contract.functions.lastTimestamp().call()
        latestQueryId = contract.functions.latestQueryId().call()
        pendingUpdate = contract.functions.pendingUpdate().call()
        witnet = contract.functions.witnet().call()
        pfs.append({
          "caption": caption,
          "contract": contract,
          "deviation": deviation,
          "heartbeat": heartbeat,
          "lastPrice": lastPrice,
          "lastTimestamp": lastTimestamp,
          "latestRequestId": latestQueryId,
          "minSecsBetweenUpdates": pfs_config['feeds'][caption].get("minSecsBetweenUpdates", 3600),
          "pendingUpdate": pendingUpdate,
          "witnet": witnet
        })
        print(f"{caption}:")
        print(f"  => Witnet:      {witnet}")
        print(f"  => Contract:    {contract.address}")        
        print(f"  => Deviation:   {deviation} %")
        print(f"  => Heartbeat:   {heartbeat} seconds")
        print(f"  => Last price:  {lastPrice / 10 ** int(caption.split('-')[2])} {pfs_config['feeds'][caption]['label']}")
        print(f"  => Last update: {datetime.datetime.fromtimestamp(lastTimestamp).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"  => Latest id:   {latestQueryId} (pending: {pendingUpdate})\n")

      else:
        print(f"{caption} => hashed as {erc2362id}, not found in the registry :/\n")

    if len(pfs) == 0:
      print("Sorry, no price feeds to poll :/")
      return

    print(f"Ok, so let's poll every {loop_interval_secs} seconds...")
    while True:
      print()
      loop_ts = int(time.time())
      for pf in pfs:
        contract = pf["contract"]
        # Poll latest update status
        try:
          lastValue = contract.functions.lastValue().call()
          status = lastValue[3]
          current_ts = int(time.time())
          elapsed_secs = current_ts - pf["lastTimestamp"]
        
          # If still waiting for an update...
          if pf["pendingUpdate"] == True:
            # A valid result has just been detected:
            if status == 200:
              pf["pendingUpdate"] = False
              pf["lastPrice"] = lastValue[0]
              elapsed_secs = lastValue[1] - pf["lastTimestamp"] 
              pf["lastTimestamp"] = lastValue[1]
              print(f"{pf['caption']} << drTxHash: {lastValue[2].hex()}, lastPrice: {lastValue[0]} after {elapsed_secs} secs")
              
            # An invalid result has just been detected:
            elif status == 400:
              pf["pendingUpdate"] = False
              latestDrTxHash = contract.functions.latestUpdateDrTxHash().call()
              latestError = contract.functions.latestUpdateErrorMessage().call()
              print(f"{pf['caption']} >< drTxHash: {latestDrTxHash.hex()}, latestError: \"{str(latestError)}\" after {elapsed_secs} secs")

            else:
              print(f"{pf['caption']} .. awaiting response from {pf['witnet']}::{pf['latestRequestId']}")
              
          # If no update is pending...
          else :
            if elapsed_secs >= pf["minSecsBetweenUpdates"] - network_witnet_resolution_secs:
              last_price = pf["lastPrice"]
              deviation = 0
              if last_price > 0:
                # ...calculate price deviation...
                try:
                  next_price = dry_run_request(contract.functions.bytecode().call())
                except:
                  # If dry run fails, assume 0 deviation as to, at least, guarantee the heartbeat periodicity is met
                  print("Dry-run request failed:")
                  print(contract.functions.bytecode().call().hex())
                  next_price = last_price
                deviation = round(100 * ((next_price - last_price) / last_price), 2)
                # If deviation is below threshold...
                if abs(deviation) < pf["deviation"] and elapsed_secs < (pf["heartbeat"] - network_witnet_resolution_secs):
                  print(f"{pf['caption']} .. {deviation} % deviation after {elapsed_secs} secs since last update")
                  # ...skip request update until, at least, another `loop_interval_secs` secs
                  continue
              # Post new update request
              reason = f"deviation is greater than {pf['deviation']} %"
              if (elapsed_secs >= pf['heartbeat'] - network_witnet_resolution_secs):
                reason = "of heartbeat and Witnet latency"
              print(f"{pf['caption']} >> Requesting update after {elapsed_secs} seconds because {reason}:")
              latestRequestId = handle_requestUpdate(
                w3,
                csv_filename,
                contract,
                network_symbol,
                network_from,
                network_gas,
                network_gas_price,
                network_tx_waiting_timeout_secs,
                network_tx_polling_latency_secs
              )
              if latestRequestId > 0:
                pf["pendingUpdate"] = True
                pf["latestRequestId"] = latestRequestId

            else:
              secs_until_next_check = pf['minSecsBetweenUpdates'] - elapsed_secs - network_witnet_resolution_secs
              if secs_until_next_check > 0:
                print(f"{pf['caption']} .. resting for another {secs_until_next_check} secs before next deviation check")
        
        # Capture exceptions while reading state from contract
        except Exception as ex:
          print(f"Exception when getting state from contract {contract.address}:\n{ex}")
      
      # Sleep just enough between loops
      preemptive_secs = loop_interval_secs - int(time.time()) + loop_ts
      if preemptive_secs > 0:
        time.sleep(preemptive_secs)

def main(args):    
    print("================================================================================")
    # Read network parameters from configuration file:
    network_config = load_network_config(args.toml_file)
    network_name = network_config['network']['name']
    network_symbol = network_config["network"].get("symbol", "ETH")
    network_provider = args.provider if args.provider else network_config['network']['provider']
    network_provider_timeout_secs = network_config['network'].get("provider_timeout_secs", 60)
    network_from = network_config["network"]["from"]
    network_gas = network_config["network"].get("gas", 4000000)
    network_gas_price = network_config["network"].get("gas_price", "estimate_medium")
    network_tx_waiting_timeout_secs = network_config["network"].get("tx_waiting_timeout_secs", 130)
    network_tx_polling_latency_secs = network_config["network"].get("tx_polling_latency_secs", 13)
    network_witnet_resolution_secs = network_config["network"].get("dr_resolution_latency_secs", 300)

    # Read pricefeeds parameters from configuration file:
    pfs_config = load_price_feeds_config(args.json_file, network_name)
    if pfs_config is None:
      print(f"Fatal: no configuration for network '{network_name}'")
      exit(1)
    
    # Open web3 provider from the arguments provided:
    w3 = Web3(Web3.HTTPProvider(
      network_provider,
      request_kwargs={'timeout': network_provider_timeout_secs}
    ))
    try:
      current_block = w3.eth.blockNumber
      print(f"Connected to '{network_name}' at block #{current_block} via {network_provider}")
    except Exception as ex:
      print(f"Fatal: connection failed to {network_provider}: {ex}")
      exit(1)

    # If network is Ethereum, and gas price was not specified, try to activate medium_gas_price_strategy: 
    if not isinstance(network_gas_price, int):
      if network_gas_price == "estimate_medium" and w3.eth.chainId == 1:
        from web3 import middleware
        from web3.gas_strategies.time_based import medium_gas_price_strategy

        # Transaction mined within 5 minutes
        w3.eth.setGasPriceStrategy(medium_gas_price_strategy)

        # Setup cache because get price is slow (it needs 120 blocks)
        w3.middleware_onion.add(middleware.time_based_cache_middleware)
        w3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
        w3.middleware_onion.add(middleware.simple_cache_middleware)

        network_gas_price = None
      else:
        if network_gas_price == "estimate_medium" and w3.eth.chainId != 1:
          print(f"Invalid gas price: {network_gas_price}. \"estimate_medium\" can only be used for mainnet (current id: {w3.eth.chainId})")
        else:
          print(f"Invalid gas price: {network_gas_price}. `gas_price` can only be an integer or \"estimate_medium\".")
        exit(1)

    # Enter infinite loop
    log_loop(
      w3,
      args.loop_interval_secs,
      args.csv_file,
      pfs_config,
      network_symbol,
      network_from,
      network_gas,
      network_gas_price,      
      network_tx_waiting_timeout_secs,
      network_tx_polling_latency_secs,
      network_witnet_resolution_secs      
    )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Connect to an Ethereum provider.')
    parser.add_argument('--toml_file', dest='toml_file', action='store', required=True,
                    help='provide the network TOML configuration file')
    parser.add_argument('--json_file', dest='json_file', action='store', required=True,
                    help='provide the price feeds JSON configuration file')
    parser.add_argument('--loop_interval_secs', dest='loop_interval_secs', action='store', type=int, required=False, default=30,
                    help='seconds after which the script triggers the state of the smart contract')
    parser.add_argument('--provider', dest='provider', action='store', required=False,
                    help='web3 provider to which the poller should connect. If not provided it reads from config')
    parser.add_argument('--csv_file', dest='csv_file', action='store', required=False, default="",
                    help='provide the CSV file in which master address balance will be logged after sending every new transaction')

    args = parser.parse_args()
    main(args)
