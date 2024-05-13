#!/usr/bin/env python3

import argparse
import contextlib
import datetime
import os
import re
import subprocess
import sys
import time

from configs import get_currency_symbol, get_network_config, get_price_feed_config, load_dfe_config, load_version
from contracts import feeds_contract
from dotenv import load_dotenv
from io import StringIO
from web3 import Web3, exceptions
from web3.logs import DISCARD
from web3.middleware import geth_poa_middleware

def handle_requestUpdate(
    w3,
    csv_filename,
    feeds,
    feed_id,
    feed_rad_hash,
    feed_latest_update_query_id,
    web3_symbol,
    web3_from,
    web3_gas,
    web3_gas_price,
    web3_provider_waiting_secs,
    web3_provider_polling_secs
  ):

    try:
      print(f" - WitnetFeeds address: {feeds.address}")      
      print(f" - Feed's id          : {feed_id}")
      print(f" - Feed's RAD hash    : {feed_rad_hash}")
      
      # Check that the account has enough balance
      balance = w3.eth.getBalance(web3_from)
      if balance == 0:
          raise Exception("Master account run out of funds")

      print(f" - Poller's account   : {web3_from}")
      print(f" - Poller's balance   : {round(balance / 10 ** 18, 5)} {web3_symbol}")

      # Apply gas price strategy, if any
      if web3_gas_price is None:
        web3_gas_price = w3.eth.generateGasPrice()
      print( " - Tx. gas price :", "{:,}".format(web3_gas_price))     
      
      if web3_gas is not None:
        print( " - Tx. gas limit :", "{:,}".format(web3_gas))

      # Estimate evm+witnet fee
      fee = feeds.functions.estimateUpdateBaseFee(web3_gas_price).call()
      print(f" - Tx. value     : {round(fee / 10 ** 18, 5)} {web3_symbol}")

      # Send Web3 transaction ..
      if web3_gas is None:
        # .. without a gas limit
        tx = feeds.functions.requestUpdate(feed_id).transact({
          "from": web3_from,
          "gasPrice": web3_gas_price,
          "value": fee
        })
      else:
        # .. with the gas limit specified in config file        
        tx = feeds.functions.requestUpdate(feed_id).transact({
          "from": web3_from,
          "gas": web3_gas,
          "gasPrice": web3_gas_price,
          "value": fee
        })

      # Log send transaction attempt
      log_master_balance(csv_filename, web3_from, balance, tx.hex())
      print(f" ~ Tx. hash      : {tx.hex()}")      

      # Wait for tx receipt and print relevant tx info upon reception
      receipt = w3.eth.wait_for_transaction_receipt(
        tx,
        web3_provider_waiting_secs,
        web3_provider_polling_secs
      )
      total_fee = balance - w3.eth.getBalance(web3_from)
      print( " > Tx. block num.:", "{:,}".format(receipt.get("blockNumber")))
      print( " > Tx. total gas :", "{:,}".format(receipt.get("gasUsed")))
      print( " > Tx. total cost:", round(total_fee / 10 ** 18, 5), web3_symbol)

    except exceptions.TimeExhausted:
      print(f"   ** Transaction is taking too long !!")
      return [ 0 ]

    except Exception as ex:
      print(f"   xx Transaction rejected: {unscape(ex)}")
      return [ 0 ]

    # Check if transaction was succesful
    if receipt['status'] == False:
      print(f"   $$ Transaction reverted !!")
      return [ -1, tx.hex() ]
    else:
      queryId = 0
      logs = feeds.events.WitnetQuery().processReceipt(receipt, errors=DISCARD)
      if len(logs) > 0:     
        queryId = logs[0].args.id
        if queryId > 0:
          print(f" <<<< Query id : {queryId}\n")
        else:
          print(f" <<<< Synchronous update.\n")
        return [ queryId, tx.hex(), total_fee ]
      else:
        print(f" ==== Previous query id : {feed_latest_update_query_id}\n")
        return [ feed_latest_update_query_id, tx.hex(), total_fee ]

def reload_config(config_file_path, network_name):
    config = load_dfe_config(config_file_path)
    network_config = get_network_config(config, network_name)
    if network_config['version'] != '2.0':
      print(f"Fatal: Network '{network_name}' not prepared for 2.0")
      exit(1)
    return config, network_config.get('address', config['contracts']['2.0']['address'])

def reload_pfs(feeds, config, network_name):
    
  captionMaxLength = 0
  ids = []
  pfs = []    

  supports = feeds.functions.supportedFeeds().call()
  for index in range(len(supports[0])):
    caption = supports[1][index]
    pf_id = supports[0][index].hex()
    rad_hash = supports[2][index].hex()
      
    print(f"{caption}:")
    routed = rad_hash.startswith("0000000000000000000000000000000000000000")
    if routed == False:
      cooldown = get_price_feed_config(config, network_name, caption, "minSecsBetweenUpdates", 3600)
      deviation = get_price_feed_config(config, network_name, caption, "deviationPercentage", 3.5)
      heartbeat = int(get_price_feed_config(config, network_name, caption, "maxSecsBetweenUpdates", 86400))
      for attempt in range(5):
        try:    
          if routed == False:
            bytecode = feeds.functions.lookupWitnetBytecode(pf_id).call()  
          else:
            bytecode = ""
          latest_price = feeds.functions.latestPrice(pf_id).call()
          latest_update_query_id = feeds.functions.latestUpdateQueryId(pf_id).call()
          pending_update = latest_price[3] == 1
          ids.append(pf_id)
          pfs.append({
            "id": pf_id,
            "bytecode": bytecode,
            "caption": caption,
            "cooldown": cooldown,
            "deviation": deviation,
            "heartbeat": heartbeat,
            "isRouted": routed,
            "latestPrice": latest_price[0],
            "latestTimestamp": latest_price[1],
            "latestUpdateQueryId": latest_update_query_id,
            "pendingUpdate": pending_update,
            "radHash": rad_hash,
            "revert": 0,
            "auto_disabled": False,
            "lastRevertedTx": "",
            "lastUpdateFailed": False,
            "lastUpdateFailedTimestamp": int(time.time()),
            "fees": [],
            "secs": []
          })
          print(f"  => ID4         : {pf_id}")
          if routed == True:
            print(f"  => Solver addr : {rad_hash[24:]}")
          else:
            print(f"  => RAD hash    : {rad_hash}")
            print(f"  => Deviation   : {deviation} %")
            print(f"  => Bytecode    : {bytecode.hex()}")
            if heartbeat > 0:
              print(f"  => Heartbeat   : {heartbeat} seconds")
            if cooldown > 0:
              print(f"  => Cooldown    : {cooldown} seconds")
          if latest_update_query_id > 0:
              if (latest_price[1] > 0):
                decimals = int(caption.split('-')[2])
                quote = caption.split('-')[1].split('/')[1]
                print(f"  => Last price  : {latest_price[0] / 10 ** decimals} {get_currency_symbol(config, quote)}")
                print(f"  => Last update : {datetime.datetime.fromtimestamp(latest_price[1]).strftime('%Y-%m-%d %H:%M:%S %Z')}")
              print(f"  => Last query  : {latest_update_query_id} (pending: {pending_update})")
          print()
          break
        except Exception as ex:
          if attempt < 4:
            print(f"  >< Attempt #{attempt}: {unscape(ex)}")
            continue
          else:
            print(f"  >< Skipped: Exception: {unscape(ex)}")
            break
      
      if len(caption) > captionMaxLength:
        captionMaxLength = len(caption)
  
  return ids, pfs, captionMaxLength

def reload_pfs_params(pfs, config, network_name):
  for pf in pfs:
    caption = pf["caption"]
    routed = pf["radHash"].startswith("0000000000000000000000000000000000000000")
    if routed == False:
      cooldown = get_price_feed_config(config, network_name, caption, "minSecsBetweenUpdates", 3600)
      deviation = get_price_feed_config(config, network_name, caption, "deviationPercentage", 3.5)
      heartbeat = int(get_price_feed_config(config, network_name, caption, "maxSecsBetweenUpdates", 86400))
      if cooldown != pf["cooldown"] or deviation != pf["deviation"] or heartbeat != pf["heartbeat"]:
        print(f"{caption} changed parameters to:")
        print(f"=> Deviation: {deviation} %")
        print(f"=> Heartbeat: {heartbeat} seconds")
        print(f"=> Cooldown : {cooldown} seconds\n")
        pf["cooldown"] = cooldown
        pf["deviation"] = deviation
        pf["heartbeat"] = heartbeat  
  
  return pfs

def handle_loop(
    w3,
    loop_interval_secs,
    csv_filename,
    config_file_path,
    config_reload_secs,
    network_name,
    web3_symbol,
    web3_address,
    web3_from,
    web3_gas,
    web3_gas_price,
    web3_finalization_secs,
    web3_max_reverts,
    web3_provider_waiting_secs,
    web3_provider_polling_secs,
    witnet_resolution_secs,
    witnet_toolkit_timeout_secs
  ):
    config, config_address = reload_config(config_file_path, network_name)
    
    feeds = feeds_contract(w3, web3_address or config_address)
    if feeds.address is None:
      print("Fatal: invalid WitnetPriceFeeds address read from {feeds_config_file_path}")
      exit(1)

    try:
      print(f"Using WitnetOracle at {feeds.functions.witnet().call()}")
      print(f"Using WitnetPriceFeeds at {feeds.address}")
    except Exception as ex:
      print(f"Uncompliant WitnetPriceFeeds at {feeds.address}")
      exit(1)

    print(f"\nOk, so let's poll every {loop_interval_secs} seconds...")
    
    reload_ts = int(time.time())
    low_balance_ts = int(time.time()) - 900
    total_finalization_secs = web3_finalization_secs + witnet_resolution_secs

    captionMaxLength = 0
    footprint = None
    ids = None
    pfs = None    
    
    while True:

      print()
      loop_ts = int(time.time())
      
      try:
        # Reload configuration file every `config_reload_secs`...
        if ids is None or (loop_ts - reload_ts) >= config_reload_secs:
          reload_ts = loop_ts
          
          try:
            config, config_address = reload_config(config_file_path, network_name)
          except:
            print(f"Warning: cannot reload configuration from {config_file_path}\n")
            continue
          
          if web3_address is None:
            if config_address != feeds.address:
              print(f"Trying to change WitnetPriceFeeds address...")
              try:
                new_feeds = feeds_contract(w3, config_address)
                print(f"=> Using WitnetOracle at {new_feeds.functions.witnet().call()}")
                print(f"=> Using WitnetPriceFeeds at {new_feeds.address}")
                feeds = new_feeds
              except Exception as ex:
                print(f"=> Exception: {ex}")

          new_footprint = feeds.functions.footprint().call().hex()
          if footprint is None or new_footprint != footprint:
            # Reload pfs and ids if the WPF contract's footprint changed 
            if footprint is not None:
                print(f"Reloading price feeds due to a footprint change detected on WitnetPriceFeeds at {feeds.address}...\n")            
            footprint = new_footprint
            ids, pfs, captionMaxLength = reload_pfs(feeds, config, network_name)
            
          else:
            # Otherwise revisit config parameters for each currently support price feed
            pfs = reload_pfs_params(pfs, config, network_name)

        # Check balance on every `loop_interval_secs`
        balance = w3.eth.getBalance(web3_from)
        time_left_secs = time_to_die_secs(balance, pfs)
        timer_out = (loop_ts - low_balance_ts) >= config_reload_secs
        if time_left_secs > 0:
          if time_left_secs <= 86400 * 3 and timer_out:
            # start warning every 900 seconds if estimated time before draining funds is less than 3 days
            low_balance_ts = loop_ts
            print(f"LOW FUNDS !!!: estimated {round(time_left_secs / 3600, 2)} hours before running out of funds")
          else:
            print(f"Time-To-Die: {round(time_left_secs / 3600, 2)} hours")

         # On every iteration, read latest prices of all currently supported pfs
        latest_prices = feeds.functions.latestPrices(ids).call()
      
      except Exception as ex:
        print(f"Main loop exception: {unscape(ex)}")
        time.sleep(1)
        continue
      
      for index in range(len(ids)):
        
        pf = pfs[index]
        id = pf['id']
        caption = pf['caption']
        caption += " " * (captionMaxLength - len(caption))

        decimals = int(caption.split('-')[2])
        quote = caption.split('-')[1].split('/')[1]
        symbol = get_currency_symbol(config, quote)

        try:     

          if pf["auto_disabled"]:
            # Skip if this pricefeed is disabled
            if pf["lastRevertedTx"] != "":
              print(f"{caption} >< too many reverts: see last reverted tx: {pf['lastRevertedTx']}")
            else:
              print(f"{caption} >< this feed is not supported anymore.")
            continue

          # Poll latest update status
          latest_price = latest_prices[index]
          status = latest_price[3]
          current_ts = int(time.time())
          elapsed_secs = current_ts - pf["latestTimestamp"]
        
          # On routed pfs: just check for spontaneous price updates
          if pf["isRouted"] == True:
            if latest_price[1] > pf["latestTimestamp"]:
              
              print(f"{caption} <> routed price updated to {latest_price[0] / 10 ** int(decimals)} {symbol}")
              pf["latestTimestamp"] = latest_price[1]
            else:
              print(f"{caption} .. expecting eventual routed update.")
            continue

          # If still waiting for an update...
          if pf["pendingUpdate"] == True:
          
            if status == 2: ##and latest_price[1] >= pf["latestTimestamp"]:
              # a finalized successfull report is detected 
              pf["lastUpdateFailed"] = False
              pf["latestPrice"] = latest_price[0]
              elapsed_secs = latest_price[1] - pf["latestTimestamp"] 
              pf["latestTimestamp"] = latest_price[1]
              pf["pendingUpdate"] = False

              print(f"{caption} << drTallyTxHash: {latest_price[2].hex()} => updated to {latest_price[0] / 10 ** int(decimals)} {symbol} (after {elapsed_secs} secs)")
              
            elif status == 3:
              # a finalized errored result is detected
              pf["pendingUpdate"] = False
              latest_response = feeds.functions.latestUpdateResponse(id).call()
              latest_error = feeds.functions.latestUpdateResultError(id).call()
              pf["lastUpdateFailed"] = True
              pf["lastUpdateFailedTimestamp"] = current_ts
              print(f"{caption} >< drTallyTxHash: {latest_response[3].hex()} => \"{str(latest_error[1])}\"")

            else:
              latest_update_query_id = pf["latestUpdateQueryId"]
              if latest_update_query_id > 0:
                if pf["latestTimestamp"] > 0:
                  print(f"{caption} .. awaiting response to query #{latest_update_query_id} (after {elapsed_secs} secs)")
                else:
                  print(f"{caption} .. awaiting first update from query #{latest_update_query_id}")
              
          # If no update is pending:
          elif pf["isRouted"] == False:
            
            if pf["lastUpdateFailed"] == False or current_ts >= pf["lastUpdateFailedTimestamp"] + pf["cooldown"] - total_finalization_secs:
              last_price = pf["latestPrice"]
              deviation = 0

              if pf["heartbeat"] == 0:
                # No heartbeat, no polling.
                continue

              elif elapsed_secs >= pf["heartbeat"] - (0 if pf["isRouted"] else total_finalization_secs):
                # Otherwise, check heartbeat condition, first:
                reason = f"of heartbeat and Witnet latency"

              elif pf['isRouted'] == False and pf['deviation'] > 0 and last_price > 0:                
                # If heartbeat condition is not met yet, then check for deviation, if required:
                try:
                  next_price = dry_run_request(
                    pf['bytecode'],
                    witnet_toolkit_timeout_secs
                  )
                except Exception as ex:
                  # ...if dry run fails, assume 0 deviation as to, at least, guarantee the heartbeat periodicity is met
                  print(f"{caption} >< Dry-run failed:", unscape(ex))
                  continue
                deviation = round(100 * ((next_price - last_price) / last_price), 2)
                
                # If deviation is below threshold...
                if abs(deviation) < pf["deviation"]:
                  # ...skip request update until, at least, another `loop_interval_secs` secs
                  print(f"{caption} .. {deviation} % deviation after {elapsed_secs} secs since last update")                  
                  continue
                else:
                  reason = f"deviation is greater than {pf['deviation']} %"

              else:
                print(f"{caption} .. expecting heartbeat condition for another {pf['heartbeat'] - elapsed_secs} secs")
                continue
                
              print(f"{caption} >> Requesting update after {elapsed_secs} seconds because {reason}:")
              result = handle_requestUpdate(
                w3,
                csv_filename,
                feeds,
                id,
                pf["radHash"],
                pf["latestUpdateQueryId"],
                web3_symbol,
                web3_from,
                web3_gas,
                web3_gas_price,
                web3_provider_waiting_secs,
                web3_provider_polling_secs
              )

              latest_update_query_id = result[0]
              if latest_update_query_id > 0:
                pf["latestUpdateQueryId"] = latest_update_query_id
                pf["pendingUpdate"] = True
                pf["reverts"] = 0

              elif latest_update_query_id < 0:
                pf["lastRevertedTx"] = result[1]
                pf["reverts"] = pf["reverts"] + 1
                if pf["reverts"] >= web3_max_reverts:
                  pf["auto_disabled"] = True

              # on fully successfull update request:
              if len(result) >= 3:                

                # update fees and secs history
                latest_fee = result[2]
                if latest_fee > 0:
                  pf["fees"].append(latest_fee)
                  if len(pf["fees"]) > 16:
                    del pf["fees"][0]
                pf["secs"].append(elapsed_secs)                
                if len(pf["secs"]) > 256:
                  del pf["secs"][0]

            else:
              secs_until_next_check = pf['cooldown'] - current_ts + pf["lastUpdateFailedTimestamp"] - total_finalization_secs
              if secs_until_next_check > 0:
                print(f"{caption} .. resting for another {secs_until_next_check} secs before next triggering check")
        
        # Capture exceptions while reading state from contract
        except Exception as ex:
          print(f"{caption} .. Exception when getting state from {feeds.address}: {unscape(ex)}")
      
      # Sleep just enough between loops
      preemptive_secs = loop_interval_secs - int(time.time()) + loop_ts
      if preemptive_secs > 0:
        time.sleep(preemptive_secs)

def main(args):    
    print("================================================================================")
    print(load_version())
    load_dotenv()

    # Read config reload period
    config_reload_secs = int(os.getenv('WPFP_CONFIG_RELEOAD_SECS') or 30)

    # Read network parameters from environment:
    network_name = os.getenv('WPFP_NETWORK_NAME')
    network_timeout_secs = int(os.getenv('WPFP_NETWORK_TIMEOUT_SECS') or 60)

    # Read web3 parameters from environment:
    web3_address = os.getenv('WPFP_WEB3_ADDRESS')
    web3_finalization_secs = int(os.getenv('WPFP_WEB3_FINALIZATION_SECS') or 60)
    web3_from = os.getenv('WPFP_WEB3_FROM')
    web3_gas = int(os.getenv('WPFP_WEB3_GAS')) if os.getenv('WPFP_WEB3_GAS') else None
    web3_gas_price = int(os.getenv('WPFP_WEB3_GAS_PRICE')) if os.getenv('WPFP_WEB3_GAS_PRICE') else None
    web3_max_reverts = int(os.getenv('WPFP_WEB3_MAX_REVERTS') or 3)
    web3_provider = args.provider if args.provider else os.getenv('WPFP_WEB3_PROVIDER')
    web3_provider_poa = bool(os.getenv('WPFP_WEB3_PROVIDER_POA'))
    web3_provider_waiting_secs = int(os.getenv('WPFP_WEB3_PROVIDER_WAITING_TIMEOUT_SECS') or 130)
    web3_provider_polling_secs = int(os.getenv('WPFP_WEB3_PROVIDER_POLLING_LATENCY_SECS') or 13)
    web3_symbol = os.getenv('WPFP_WEB3_SYMBOL') or "ETH"

    # Read witnet parameters from environment:
    witnet_resolution_secs = int(os.getenv('WPFP_WITNET_RESOLUTION_SECS') or 300)
    witnet_toolkit_timeout_secs = int(os.getenv('WPFP_WITNET_TOOLKIT_TIMEOUT_SECS') or 15)

    # Echo timers set-up:
    print(f"Loop interval period  : {'{:,}'.format(args.loop_interval_secs)}\"")
    print(f"Config reload period  : {'{:,}'.format(config_reload_secs)}\"")
    print(f"Web3 finalization time: {'{:,}'.format(web3_finalization_secs)}\"")
    print(f"Witnet resolution time: {'{:,}'.format(witnet_resolution_secs)}\"")
    print(f"Witnet toolkit timeout: {'{:,}'.format(witnet_toolkit_timeout_secs)}\"")

    # Read pricefeeds config path, and config itself:
    config_path = args.json_path if args.json_path else os.getenv('WPFP_CONFIG_PATH')
    if config_path is None:
      print(f"Fatal: no config path was set!")
      exit(1)
    elif load_dfe_config(config_path) is None:
      print(f"Fatal: cannot read configuration file")
      exit(1)
    
    # Create Web3 object
    w3 = Web3(Web3.HTTPProvider(
      web3_provider,
      request_kwargs={'timeout': network_timeout_secs}
    ))

    # Inject POA middleware, if necessary
    if web3_provider_poa:
      w3.middleware_onion.inject(geth_poa_middleware, layer=0)
      print(f"Injected geth_poa_middleware.")

    # Apply appropiate gas price strategy if no integer value is specified in `gas_price`
    if not isinstance(web3_gas_price, int):      
      # If network is Ethereum mainnet, and "estimate_medium" is specied as `gas_price`, try to activate `medium_gas_price_strategy`
      if web3_gas_price == "estimate_medium":        
        if w3.eth.chainId == 1:
          from web3 import middleware
          from web3.gas_strategies.time_based import medium_gas_price_strategy

          # Transaction mined within 5 minutes
          w3.eth.setGasPriceStrategy(medium_gas_price_strategy)

          # Setup cache because get price is slow (it needs 120 blocks)
          w3.middleware_onion.add(middleware.time_based_cache_middleware)
          w3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
          w3.middleware_onion.add(middleware.simple_cache_middleware)

          web3_gas_price = None
          print("Gas price strategy: estimate_medium")
    
        else:          
          # "estimate_medium" strategy not supported in networks other than Ethereum mainnet
          print(f"Invalid gas price: {web3_gas_price}. \"estimate_medium\" can only be used for mainnet (current id: {w3.eth.chainId})")
          exit(1)
      
      # If no `gas_price` value is specified at all, try to activate general RPC gas price strategy:
      elif web3_gas_price is None:
        from web3.gas_strategies.rpc import rpc_gas_price_strategy
        w3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
        print("Gas price strategy: eth_gasPrice")

      # Exit if anything other text is specified in `gas_price`,   
      else:
        print(f"Invalid gas price: {web3_gas_price}.")
        exit(1)

    else:    
      print(f"Gas price strategy: invariant ({'{:,}'.format(web3_gas_price)})")

    # Connect to the Web3 provider
    try:
      current_block = w3.eth.blockNumber
      print(f"Connected to '{network_name}' at block #{current_block} via {web3_provider}")      

    except Exception as ex:
      print(f"Fatal: connection failed to {web3_provider}: {unscape(ex)}")
      exit(1)

    # Log Web3 client version
    try:
      print(f"Web3 client: {w3.clientVersion}")
    except Exception as ex:
      print(f"RPC provider does not support web3_clientVersion method.")

    # Enter infinite loop
    handle_loop(
      w3,
      args.loop_interval_secs,
      args.csv_file,
      config_path,
      config_reload_secs,
      network_name,
      web3_symbol,
      web3_address,
      web3_from,
      web3_gas,
      web3_gas_price,      
      web3_finalization_secs,
      web3_max_reverts,
      web3_provider_waiting_secs,
      web3_provider_polling_secs,
      witnet_resolution_secs,
      witnet_toolkit_timeout_secs
    )

def avg_fees(pfs):
  total_fees = 0
  total_records = 0
  for pf in pfs:
    if len(pf["fees"]) > 0:
      total_fees += sum(pf["fees"])
      total_records += len(pf["fees"])
  if total_records > 0:
    return total_fees / total_records
  else:
    return 0

def dry_run_request(bytecode, timeout_secs):
  cmdline = "npx witnet-toolkit trace-query --hex "
  cmdline += bytecode.hex()
  cmdline += " | tail -n 2 | head -n 1 | awk -F: '{ print $3 }' | sed 's/ //g' | tr -d \"│\""

  # Dry-run result needs to be fetched from temporary file, 
  # because of https://bugs.python.org/issue30154.
  with open("tmp.out", "w+") as output:
    process = subprocess.Popen(
      cmdline,
      stdout = output,
      shell = True,
    )
    process.wait(timeout=timeout_secs)

  with open("tmp.out", "r") as output:
    if os.stat("tmp.out").st_size == 0:
      raise Exception(f"Timeout while trying data request ({timeout_secs} secs)")
    return int(output.read())

def log_exception_state(addr, reason):
  # log the error and wait 1 second before next iteration
  print(f"Exception while getting state from {addr}:\n{reason}")
  time.sleep(1)

def log_master_balance(csv_filename, addr, balance, txhash):
  if csv_filename is not None:
    try:
      with open(csv_filename, "a", encoding="utf-8") as csv_file:
        readable_ts = datetime.datetime.fromtimestamp(int(time.time())).strftime('%Y-%m-%d %H:%M:%S %Z')
        row = f"\"{os.path.splitext(os.path.basename(csv_filename))[0]}\";\"{addr}\";\"{readable_ts}\";\"{balance}\";\"{txhash}\""
        csv_file.write(row + '\n')
    except Exception as ex:
      return

@contextlib.contextmanager
def stdoutIO(stdout=None):
  old = sys.stdout
  if stdout is None:
    stdout = StringIO()
  sys.stdout = stdout
  yield stdout
  sys.stdout = old

def time_to_die_secs(balance, pfs):
  total_speed = 0
  total_avg_fee = avg_fees(pfs)
  for pf in pfs:
    if len(pf["secs"]) > 0:
      pf_secs = sum(pf["secs"]) / len(pf["secs"])
    else:
      pf_secs = pf["heartbeat"]    
    if pf_secs > 0:
      if len(pf["fees"]) > 0:    
        pf_fees = sum(pf["fees"]) / len(pf["fees"])
      else:
        pf_fees = total_avg_fee
      total_speed += (pf_fees / pf_secs)
  if total_speed > 0:
    return balance / total_speed
  else:
    return 0

def unscape(ex):
  src = str(ex)
  slashes = 0 # count backslashes
  dst = ""
  for loc in range(0, len(src)):
      char = src[loc]
      if char == "\\":
          slashes += 1
          if slashes == 2:
              # remove double backslashes
              slashes = 0
      elif slashes == 0:
          # normal char
          dst += char 
      else: # slashes == 1
          if char == '"':
              # double-quotes
              dst += char 
          elif char == "'":
              # remove single-quote
              dst += char 
          else:
              dst += "\\" + char # keep backslash-escapes like \n or \t
          slashes = 0
  return dst

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Connect to an Ethereum provider.')
    parser.add_argument('--json_path', dest='json_path', action='store', required=False,
                    help='provide path to price feeds configuration file')
    parser.add_argument('--loop_interval_secs', dest='loop_interval_secs', action='store', type=int, required=False, default=30,
                    help='seconds after which the script triggers the state of the smart contract')
    parser.add_argument('--provider', dest='provider', action='store', required=False,
                    help='web3 provider to which the poller should connect. If not provided it reads from config')
    parser.add_argument('--csv_file', dest='csv_file', action='store', required=False, default="",
                    help='provide the CSV file in which master address balance will be logged after sending every new transaction')

    args = parser.parse_args()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  
    main(args)
