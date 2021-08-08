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
executed_trades = {s: [] for s in all_symbols} #running list of executed orders
all_orders = []
order_index = 0


book = {s: {"buy": None, "sell": None} for s in all_symbols}
def best_book(symbol, dir):
    return book[symbol][dir]
    
def has_book(symbols):
    if type(symbols) == str:
        symbols = [symbols]
    for s in symbols:
        if book[s]["buy"] is None or book[s]["sell"] is None:
            return False
    
    return True

def update_book(message):
    global book
    buy_side = message["buy"]
    sell_side = message["sell"]
    symbol = message["symbol"]
    
        ## price
    if len(buy_side) > 0:
        book[symbol]["buy"] = buy_side[0]
    if len(sell_side) > 0:
        book[symbol]["sell"] = sell_side[0]
    return 

positions = {s: 0 for s in all_symbols}
def update_positions(message):
    global positions
    positions[message["symbol"]] += message["size"] * (1 if (message["dir"] == "BUY") else -1)


def update_positions_from_ack(message):
    global positions, convert_history
    order_id = message["order_id"]
    if order_id not in convert_history:
        return
    order = convert_history[order_id]
    factor = (1 if (order["dir"] == "BUY") else -1)
    amt = order["size"]
    if order["symbol"] == "XLF":
        amt = amt // 10
        print("confirm XLF convert")
        positions["XLF"] += factor * amt * 10
        positions["BOND"] -= factor * amt * 3
        positions["GS"] -= factor * amt * 2
        positions["MS"] -= factor * amt * 3
        positions["WFC"] -= factor * amt * 2
    elif order["symbol"] == "VALE":
        print("confirm VALE convert")
        positions["VALE"] += factor * amt
        positions["VALBZ"] -= factor * amt
        

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
    if symbol == "XLF":
        print("ORDER", order)
    last_symbol_order[symbol] = time.time()
    
    write_to_exchange(exchange, order)
    order_count += 1


convert_history = {}

def convert(symbol, dir, size):
    global order_count, last_convert_time
    order = {"type": "convert", "order_id": order_count, "symbol": symbol, "dir": dir, "size": size}
    convert_history[order_count] = order
    last_convert_time = time.time()
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
            do_multi_trade(["VALBZ"], ["VALE"])
            if last_symbol_order["VALBZ"] < last_symbol_order["VALE"]:
                do_order("VALBZ", "BUY", VALBZ_buy[0], VALBZ_buy[1])
            else:
                do_order("VALE", "SELL", VALE_sell[0], VALE_sell[1])
        
        else:
            ## sell VALBZ, buy VALE
            do_multi_trade(["VALE"], ["VALBZ"])

    else:
        return

def do_multi_trade(buy_side, sell_side):
    trade_symbol = get_oldest_symbol(buy_side + sell_side)
    if trade_symbol in buy_side:
        trade_dir = "buy"
    elif trade_symbol in sell_side:
        trade_dir = "sell"
    else:
        print("WARNING: WEIRD SPOT 1")
        return
    my_order = best_book(trade_symbol, trade_dir)
    do_order(trade_symbol, trade_dir.upper(), my_order[0], my_order[1])



def trade_etf(message):
    edge = 3
    conversion = 100
    
    if not has_book(["BOND", "GS", "MS", "WFC", "XLF"]):
        return
    
    
    GS_buy = book["GS"]["buy"]
    GS_sell = book["GS"]["sell"]
    MS_buy = book["MS"]["buy"]
    MS_sell = book["MS"]["sell"]
    WFC_buy = book["WFC"]["buy"]
    WFC_sell = book["WFC"]["sell"]
    XLF_buy = book["XLF"]["buy"]
    XLF_sell = book["XLF"]["sell"]

    BOND_fair = 1000.0
    GS_fair = (GS_buy[0] + GS_sell[0]) / 2.0
    MS_fair = (MS_buy[0] + MS_sell[0]) / 2.0
    WFC_fair = (WFC_buy[0] + WFC_sell[0]) / 2.0
    XLF_fair = (XLF_buy[0] + XLF_sell[0]) / 2.0
    
    
    basket_fair = (3 * BOND_fair + 2 * GS_fair + 3 * MS_fair + 2 * WFC_fair) / 10
    # print("basket/xlf fair", basket_fair - XLF_fair, basket_fair, XLF_fair)
    
    ## if basket sum > ETF, we should buy ETF and sell basket
    if basket_fair > XLF_fair + edge:
        # consider adding a check to not trade bonds at a bad price
        # print("buying xlf, selling basket")
        do_multi_trade(["XLF"], [])
        # do_multi_trade(["XLF"], ["BOND", "GS", "MS", "WFC"])
        return
    elif basket_fair < XLF_fair:
        # print("selling xlf, buying basket")
        do_multi_trade([], ["XLF"])
        # do_multi_trade(["BOND", "GS", "MS", "WFC"], ["XLF"])
        return

def num_traded(symbol):
    sum = 0
    for arr in executed_trades[symbol]:
        sum += arr[1]
    return sum

def exec_fair_value(symbol):
    sum = 0
    num = 0
    for arr in executed_trades[symbol]:
        sum += arr[0] * arr[1]
        num += arr[1]
    
    if num != 0:
        return sum / num
    else:
        return 0

def update_executed(message):
    global executed_trades
    symbol = message["symbol"]
    price = message["price"]
    size = message["size"]
    
    if symbol != "BOND":
        executed_trades[symbol].append([price, size])
    return
    
# def convert_ADR():
#     global positions
#     if positions["VALE"]

def convert_ETF():
    global positions
    global book
    edge = 3
    conversion = 100
    print("hihi")
    if not has_book(["BOND", "GS", "MS", "WFC", "XLF"]):
        return
    
    hundred = ["GS", "MS", "WFC", "XLF"]
    
    GS_buy = book["GS"]["buy"]
    GS_sell = book["GS"]["sell"]
    MS_buy = book["MS"]["buy"]
    MS_sell = book["MS"]["sell"]
    WFC_buy = book["WFC"]["buy"]
    WFC_sell = book["WFC"]["sell"]
    XLF_buy = book["XLF"]["buy"]
    XLF_sell = book["XLF"]["sell"]

    BOND_fair = 1000.0
    GS_fair = (GS_buy[0] + GS_sell[0]) / 2.0
    MS_fair = (MS_buy[0] + MS_sell[0]) / 2.0
    WFC_fair = (WFC_buy[0] + WFC_sell[0]) / 2.0
    XLF_fair = (XLF_buy[0] + XLF_sell[0]) / 2.0
    
    
    basket_fair = (3 * BOND_fair + 2 * GS_fair + 3 * MS_fair + 2 * WFC_fair) / 10.0

    for symbol in hundred:
        if symbol == "XLF":
            # if positions[symbol] > 80:
            #     ## convert ETF to individual stock
            #     if basket_fair >  XLF_fair + conversion/40:
            #         convert()

            # elif positions[symbol] < -80:
            #     pass
            print("po", positions[symbol])
            if positions["XLF"] >= 100:
                convert("XLF", "SELL", 80)
            elif positions["XLF"] <= -100:
                convert("XLF", "BUY", 80)
        else:
            pass
        

        
def allowed_positions(message):
    pass

def time_since(prev_time):
    return time.time() - last_reset_time


TIME_BETWEEN_CONVERT = 3.0
last_convert_time = 0

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

        if time_since(last_convert_time) > TIME_BETWEEN_CONVERT:
            # pass
            # continue
            print("helo")
            convert_ETF()
            # convert_ADR()
        
        if message["type"] == "close":
            print("The round has ended")
            break
        elif message["type"] == "book":
            update_book(message)
            if message["symbol"] == "BOND":
                trade_bonds(message)
            elif message["symbol"] == "VALBZ" or message["symbol"] == "VALE":
                # continue
                trade_adr(message)
            else:
                trade_etf(message)
        elif message["type"] == "fill":
            update_positions(message)
        elif message["type"] == "trade":
            update_executed(message)
        elif message["type"] == "ack":
            update_positions_from_ack(message)

# def liquidate(symbol):
#     if positions[symbol] 


if __name__ == "__main__":
    main()
