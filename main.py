#!/usr/bin/python
# ~~~~~==============   HOW TO RUN   ==============~~~~~
# 1) Configure things in CONFIGURATION section
# 2) Change permissions: chmod +x bot.py
# 3) Run in loop: while true; do ./bot.py; sleep 1; done

from __future__ import print_function

import sys
import socket
import json
import time

# ~~~~~============== CONFIGURATION  ==============~~~~~
# replace REPLACEME with your team name!
team_name = "THAYER"
# This variable dictates whether or not the bot is connecting to the prod
# or test exchange. Be careful with this switch!
test_mode = True

# This setting changes which test exchange is connected to.
# 0 is prod-like
# 1 is slower
# 2 is empty
test_exchange_index = 0
prod_exchange_hostname = "production"

port = 25000 + (test_exchange_index if test_mode else 0)
exchange_hostname = "test-exch-" + team_name if test_mode else prod_exchange_hostname

# ~~~~~============== NETWORKING CODE ==============~~~~~
def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((exchange_hostname, port))
    return s.makefile("rw", 1)


def write_to_exchange(exchange, obj):
    json.dump(obj, exchange)
    exchange.write("\n")


def read_from_exchange(exchange):
    return json.loads(exchange.readline())


# ~~~~~============== MAIN LOOP ==============~~~~~

all_symbols = ["BOND", "VALBZ", "VALE", "GS", "MS", "WFC", "XLF"]

order_count = 0
book = {s: {"buy": None, "sell": None} for s in all_symbols}
executed_trades = {s: {"buy": None, "sell": None} for s in all_symbols} #running list of executed orders
positions = {}
all_orders = []
order_index = 0


last_symbol_order = {s: 0 for s in all_symbols}

def get_oldest_symbol(symbols):
    best_symbol = symbols[0]
    best_time = float("inf")
    for s in symbols:
        if last_symbol_order[s] < best_time:
            best_symbol = s
            best_time = last_symbol_order[s]
    return best_symbol
    

RESET_ORDERS_DELAY = 1.0
last_reset_time = time.time()

def do_order(symbol, dir, price, size):
    global order_count
    order = {"type": "add", "order_id": order_count, "symbol": symbol, "dir": dir, "price": price, "size": size}
    last_symbol_order[symbol] = time.time()
    
    write_to_exchange(exchange, order)
    order_count += 1


def trade_bonds(message):
    buy_side = message["buy"]
    sell_side = message["sell"]
    if len(buy_side) > 0:
        best_buy = buy_side[0]
        if best_buy[0] > 1000:
            do_order("BOND", "SELL", best_buy[0], best_buy[1])
            return

    if len(sell_side) > 0:
        best_sell = sell_side[0]
        if best_sell[0] < 1000:
            do_order("BOND", "BUY", best_sell[0], best_sell[1])
            return

def trade_adr(message):
    global book
    ## use VALBZ (liquid) to price VALE (illiquid)

    if has_book(["VALBZ", "VALE"]):

        VALBZ_buy = book["VALBZ"]["buy"]
        VALBZ_sell = book["VALBZ"]["sell"]
        VALE_buy = book["VALE"]["buy"]
        VALE_sell = book["VALE"]["sell"]

        VALBZ_fair = (VALBZ_buy[0] + VALBZ_sell[0]) / 2.0
        VALE_fair = (VALE_buy[0] + VALE_sell[0]) / 2.0
        
        ## if VALE buy is more expensive than VALBZ, then buy VALBZ and sell VALE
        if VALE_fair > VALBZ_fair:
            ## buy VABLZ, sell VALE
            if last_symbol_order["VALBZ"] < last_symbol_order["VALE"]:
                do_order("VALBZ", "BUY", VALBZ_buy[0], VALBZ_buy[1])
            else:
                do_order("VALE", "SELL", VALE_sell[0], VALE_sell[1])
        
        else:
            ## sell VALBZ, buy VALE
            if last_symbol_order["VALBZ"] < last_symbol_order["VALE"]:
                do_order("VALBZ", "SELL", VALBZ_sell[0], VALBZ_sell[1])
            else:
                do_order("VALE", "BUY", VALE_buy[0], VALE_buy[1])

    else:
        return

def trade_etf(message):
    edge = 3
    conversion = 100
    GS_buy = book["VALBZ"]["buy"]
    GS_sell = book["VALBZ"]["sell"]
    MS_buy = book["VALE"]["buy"]
    MS_sell = book["VALE"]["sell"]
    WFC_buy = book["VALBZ"]["buy"]
    WFC_sell = book["VALBZ"]["sell"]
    XLF_buy = book["VALE"]["buy"]
    XLF_sell = book["VALE"]["sell"]

    BOND_fair = 1000.0
    GS_fair = (GS_buy[0] + GS_sell[0]) / 2.0
    MS_fair = (MS_buy[0] + MS_sell[0]) / 2.0
    WFC_fair = (WFC_buy[0] + WFC_sell[0]) / 2.0
    XLF_fair = (XLF_buy[0] + XLF_sell[0]) / 2.0
    
    
    ## if basket sum > ETF, we should buy ETF and sell basket
    if ((3*BOND_fair + 2*GS_fair + 3*MS_fair + 2* WFC_fair) > (XLF_fair+ edge + conversion//4)):
        trade_symbol = get_oldest_symbol(["BOND", "MS", "GS", "WFC", "XLF"]) # ignoring bonds for now
        trade_dir = None
        if trade_symbol == "XLF":
            do_order(trade_symbol, "BUY", XLF_buy[0], XLF_buy[1])
        else:
            do_order(trade_symbol, "SELL", XLF_buy[0], XLF_buy[1])
        return
    elif ((3*BOND_fair + 2*GS_fair + 3*MS_fair + 2* WFC_fair+ edge + conversion//4) < (XLF_fair)):
        do_order("XLF", "SELL", XLF_sell[0], XLF_sell[1])
        return

    return
          
def has_book(symbols):
    if type(symbols) == str:
        symbols = [symbols]
    for s in symbols:
        if book[s]["buy"] is None or book[s]["sell"] is None:
            return False
    return True

def update_positions(message):
    global positions
    positions[message["symbol"]] += message["size"] * (1 if (message["dir"] == "BUY") else -1)

def update_book(message):
    global book
    buy_side = message["buy"]
    sell_side = message["sell"]
    symbol = message["symbol"]
    if symbol != "BOND":
        ## price
        if len(buy_side) > 0:
            book[symbol]["buy"] = buy_side[0]
        if len(sell_side) > 0:
            book[symbol]["sell"] = sell_side[0]
    return 

def update_executed(message):
    global executed_trades
    symbol = message["symbol"]
    price = message["price"]
    size = message["size"]
    
    if symbol != BOND:
        executed_trades[symbol].append()
    
# def convert_ADR():
#     global positions
#     if positions["VALE"]

def convert_ETF():
    global positions
    hundred = ["XLF, "]
    if positions["XLF"] > 85:
        pass
    elif positions["XLF"] < -85:
        pass
        
    pass
    
    
    
def allowed_positions(message):
    pass

def time_since(prev_time):
    return time.time() - last_reset_time


def main():
    global exchange, positions, book
    exchange = connect()
    write_to_exchange(exchange, {"type": "hello", "team": team_name.upper()})
    hello_from_exchange = read_from_exchange(exchange)
    # A common mistake people make is to call write_to_exchange() > 1
    # time for every read_from_exchange() response.
    # Since many write messages generate marketdata, this will cause an
    # exponential explosion in pending messages. Please, don't do that!
    print("The exchange replied:", hello_from_exchange, file=sys.stderr)
    initial_positions = hello_from_exchange["symbols"]
    for info in initial_positions:
        positions[info["symbol"]] = info["position"]

    
    while True:
        message = read_from_exchange(exchange)
        if time_since(last_reset_time) > RESET_ORDERS_DELAY:
            pass
        
        if message["type"] == "close":
            print("The round has ended")
            break
        elif message["type"] == "book":
            update_book(message)
            if message["symbol"] == "BOND":
                trade_bonds(message)
            elif message["symbol"] == "VALBZ" or message["symbol"] == "VALE":
                trade_adr(message)
            else:
                trade_etf(message)
        elif message["type"] == "fill":
            update_positions(message)
        elif message["type"] == "trade":
            update_executed(message)




if __name__ == "__main__":
    main()
