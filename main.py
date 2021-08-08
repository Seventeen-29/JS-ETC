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
order_index = 0
unhedged = 0


book = {s: {"buy": None, "sell": None} for s in all_symbols}
def best_book(symbol, dir):
    ## returns the best price and quantity of the stock
    return book[symbol][dir]
    
def has_book(symbols):
    ## checks if the book values are in place
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
    
all_orders = {}

RESET_ORDERS_DELAY = 1.0
last_reset_time = time.time()

def do_order(symbol, dir, price, size):
    global order_count
    if size < 0:
        size = -size
        if dir == "BUY":
            dir = "SELL"
        elif dir == "SELL":
            dir = "BUY"
    order = {"type": "add", "order_id": order_count, "symbol": symbol, "dir": dir, "price": price, "size": size}
    last_symbol_order[symbol] = time.time()
    all_orders[order_count] = time.time()
    
    write_to_exchange(exchange, order)
    order_count += 1

CANCEL_DELAY = 50 / 1000.0

def cancel_hanging_orders():
    to_del = []
    for id, t in all_orders.items():
        if time_since(t) > CANCEL_DELAY:
            to_del += [id]
    for id in to_del:
        del all_orders[id]
        cancel(id)



convert_history = {}

def convert(symbol, dir, size):
    global order_count, last_convert_time
    order = {"type": "convert", "order_id": order_count, "symbol": symbol, "dir": dir, "size": size}
    convert_history[order_count] = order
    last_convert_time = time.time()
    write_to_exchange(exchange, order)
    order_count += 1

def cancel(order_id):
    order = {"type": "cancel", "order_id": order_id}


def trade_bonds(message):
    do_order("BOND", "SELL", 1001, 50)
    do_order("BOND", "BUY", 999, 50)

    # buy_side = message["buy"]
    # sell_side = message["sell"]
    # if len(buy_side) > 0:
    #     best_buy = buy_side[0]
    #     if best_buy[0] > 1000:
    #         do_order("BOND", "SELL", best_buy[0], best_buy[1])
    #         return

    # if len(sell_side) > 0:
    #     best_sell = sell_side[0]
    #     if best_sell[0] < 1000:
    #         do_order("BOND", "BUY", best_sell[0], best_sell[1])
    #         return

def trade_adr(message):
    global book
    ## use VALBZ (liquid) to price VALE (illiquid)

    edge = 3

    if has_book(["VALBZ", "VALE"]):

        VALBZ_buy = book["VALBZ"]["buy"]
        VALBZ_sell = book["VALBZ"]["sell"]
        VALE_buy = book["VALE"]["buy"]
        VALE_sell = book["VALE"]["sell"]

        VALBZ_fair = (VALBZ_buy[0] + VALBZ_sell[0]) / 2.0
        VALE_fair = (VALE_buy[0] + VALE_sell[0]) / 2.0

        VALBZ_time_fair = exec_fair_value("VALBZ")
        VALE_time_fair = exec_fair_value("VALE")
        
        ## if VALE buy is more expensive than VALBZ, then buy VALBZ and sell VALE
        if VALE_time_fair > VALBZ_time_fair + edge:
            ## buy VABLZ, sell VALE
            ## trade VALE 
            ## sell VALE
            # num = min(VALBZ_sell[1], VALE_buy[1])
            do_order("VALE", "SELL", VALE_buy[0], VALE_buy[1])
            # do_multi_trade(["VALBZ"], ["VALE"], [num], [num])
            return        
        elif VALE_time_fair + edge < VALBZ_time_fair:
            ## sell VALBZ, buy VALE
            # num = min(VALBZ_buy[1], VALE_sell[1])
            # do_multi_trade(["VALE"], ["VALBZ"], [num], [num])
            do_order("VALE", "BUY", VALE_sell[0], VALE_sell[1])
            return
    else:
        return

# def do_multi_trade(buy_side, sell_side, buy_qty_arr, sell_qty_arr):
#     trade_symbol = get_oldest_symbol(buy_side + sell_side)
#     if trade_symbol in buy_side:
#         my_order = best_book(trade_symbol, "sell") # buy at the best sell price
#         do_order(trade_symbol, "BUY", my_order[0], buy_qty_arr[buy_side.index(trade_symbol)])
#     elif trade_symbol in sell_side:
#         my_order = best_book(trade_symbol, "buy")
#         do_order(trade_symbol, "SELL", my_order[0], sell_qty_arr[sell_side.index(trade_symbol)])
#     else:
#         print("WARNING: WEIRD SPOT 1")
#         return

def do_multi_trade(buy_side, sell_side, buy_qty_arr, sell_qty_arr):
    for i in range(len(buy_side)):
        trade_symbol = buy_side[i]
        my_order = best_book(trade_symbol, "sell") # buy at the best sell price
        do_order(trade_symbol, "BUY", my_order[0], buy_qty_arr[i])
    
    for i in range(len(sell_side)):
        trade_symbol = sell_side[i]
        my_order = best_book(trade_symbol, "buy") # buy at the best sell price
        do_order(trade_symbol, "SELL", my_order[0], sell_qty_arr[i])
    
        return



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
    
    GS_time_fair = exec_fair_value("GS")
    MS_time_fair = exec_fair_value("MS")
    WFC_time_fair = exec_fair_value("WFC")
    XLF_time_fair = exec_fair_value("XLF")
    
    basket_fair = (3 * BOND_fair + 2 * GS_fair + 3 * MS_fair + 2 * WFC_fair) / 10
    
    basket_time_fair = (3 * BOND_fair + 2 * GS_time_fair + 3 * MS_time_fair + 2 * WFC_time_fair) / 10
    
    # print("basket/xlf fair", basket_fair, XLF_fair)
    # print("[TIME AVG] basket/xlf fair", basket_time_fair, XLF_time_fair)
    
    ## if basket sum > ETF, we should buy ETF and sell basket
    if basket_time_fair > XLF_time_fair + edge:
        # consider adding a check to not trade bonds at a bad price
        # print("buying xlf, selling basket")
        # do_multi_trade(["XLF"], [])
        # do_multi_trade(["XLF"], ["BOND", "GS", "MS", "WFC"])

        ## buying num amount of ETF 
        num = XLF_sell[1]
        if num < 10:
            do_order("XLF", "BUY", XLF_sell[0], num)
            ## buy num ETF
        else:
            num = num - num%10
            nt = num // 10
            ## buy num ETF
            ## sell 3 bond, 2 gs, 3 ms, 2 wfc    
            do_multi_trade(["XLF"], ["BOND", "GS", "MS", "WFC"], [num], [3*nt, 2*nt, 3*nt, 2*nt])
        return 
    elif basket_time_fair < XLF_time_fair:
        num = XLF_buy[1]
        # print("selling xlf, buying basket")
        # do_multi_trade([], ["XLF"])
        # do_multi_trade(["BOND", "GS", "MS", "WFC"], ["XLF"])
        if num < 10:
            ## just sell ETF
            do_order("XLF", "SELL", XLF_buy[0], num)
            pass
        else: 
            num = num - (num % 10)
            nt = num // 10
            ## sell num ETF
            ## buy 3 bond, 3 gs, 3 ms, 2 wfc
            do_multi_trade(["BOND", "GS", "MS", "WFC"],["XLF"], [3*nt, 2*nt, 3*nt, 2*nt],[num])
        return

def num_traded(symbol):
    sum = 0
    for arr in executed_trades[symbol]:
        sum += arr[1]
    return sum
    

def exec_fair_value(symbol):
    if symbol not in executed_trades:
        return 0
ons["VALBZ"] -= factor * amt
        


last_symbol_order = {s: 0 for s in all_symbols}

def get_oldest_symbol(symbols):
    best_symbol = symbols[0]
    best_time = float("inf")
    for s in symbols:
    sum = 0
    num = 0
    for arr in executed_trades[symbol]:
        sum += arr[0] * arr[1]
        num += arr[1]
    
    if num != 0:
        return (sum * 1.0) / num
    else:
        return 0

def update_executed(message):
    global executed_trades
    symbol = message["symbol"]
    price = message["price"]
    size = message["size"]
    
    if symbol != "BOND":
        executed_trades[symbol].append([price, size])
        if(len(executed_trades[symbol]) > 20):
            executed_trades[symbol] = executed_trades[symbol][1:]

    return
    
def convert_ADR():
    global positions
    global book
    edge = 1
    conversion  = 10

    VALBZ_buy = book["VALBZ"]["buy"]
    VALBZ_sell = book["VALBZ"]["sell"]
    VALE_buy = book["VALE"]["buy"]
    VALE_sell = book["VALE"]["sell"]

    VALBZ_fair = (VALBZ_buy[0] + VALBZ_sell[0]) / 2.0
    VALE_fair = (VALE_buy[0] + VALE_sell[0]) / 2.0

    if positions["VALE"] > 8 or positions["VALBZ"] < -8:
        ## we want to convert VALE => VALBZ
        if VALBZ_fair > VALE_fair + conversion/4.0:
            convert("VALE", "SELL", 4)
            return  
        if positions["VALE"] == 10 or positions["VALBZ"] == -10:
            convert("VALE", "SELL", 4)
            return
    elif positions["VALE"] < -8 or positions["VALBZ"] > 8:
        ## we want to convert VALBZ to VALE
        #### FIX THIS SO IT CHECKS A BIT AT LEAST
        if VALE_fair > VALBZ_fair + conversion/4.0:
            convert("VALE", "BUY", 4)
            return
        if positions["VALE"] == -10 or positions["VALBZ"] == 10:
            convert("VALE", "BUY", 4)
            return
    return
    

def convert_ETF():
    global positions
    global book
    edge = 1
    conversion = 100
    
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
            CONVERT_THRESHOLD = 80
            CONVERT_AMT = 40
            if positions[symbol] > CONVERT_THRESHOLD: ## we have too many ETF
                ## convert ETF to individual stock
                if basket_fair >  XLF_fair + conversion / CONVERT_AMT:
                    print("CONVERT XLF SELL")
                    convert("XLF", "SELL", CONVERT_AMT)
                    return
            elif positions[symbol] < -CONVERT_THRESHOLD: ## too little ETF
                if basket_fair +  conversion/CONVERT_AMT< XLF_fair:
                    print("CONVERT XLF BUY")
                    ## we will convert individual stocks to ETF
                    convert("XLF", "BUY", CONVERT_AMT)
                    return
        else:
            if positions[symbol] > 80: ## we have too much of an individual stock
                ## convert individual stock to ETC
                print("CONVERT XLF BUY")
                ## we will convert individual stocks to ETF
                convert("XLF", "BUY", CONVERT_AMT)
                return
            elif positions[symbol] < -80: ## we have too little of an invidual sotck
                print("CONVERT XLF SELL")
                convert("XLF", "SELL", CONVERT_AMT)
                return       
        
def clear_books():
    global books
    global positions
    target_amt = positions["XLF"] / 10
    target_xlf = int(target_amt * 10)
    target_gs = -int(target_amt * 2)
    target_ms = -int(target_amt * 3)
    target_wfc = -int(target_amt * 2)

    gs_change = target_gs - positions["GS"]
    ms_change = target_ms - positions["MS"]
    wfc_change = target_wfc - positions["WFC"]
    print(positions["XLF"], target_gs, target_ms, target_wfc)
    print(gs_change, ms_change, wfc_change)


    clear_helper("GS", gs_change)
    clear_helper("MS", ms_change)
    clear_helper("WFC", wfc_change)


def clear_helper(symbol, size):
    if size < 0:
        size = -size
        dir = "SELL"
        price = best_book(symbol, "buy")
    else:
        dir = "BUY"
        price = best_book(symbol, "sell")
    do_order(symbol, dir, price, size)



def allowed_positions(message):
    pass

def time_since(prev_time):
    return time.time() - last_reset_time

TIME_BETWEEN_CONVERT = 3.0
last_convert_time = time.time()

TIME_BETWEEN_TRADES = 50 / 1000.0
last_trade_time = time.time()

TIME_BETWEEN_CLEAR_BOOKS = 1
last_clear_time = time.time()

def main():
    global exchange, positions, book, last_trade_time, last_clear_time
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

        cancel_hanging_orders()
        if time_since(last_reset_time) > RESET_ORDERS_DELAY:
            pass
        
        if message["type"] == "close":
            print("The round has ended")
            break
        elif message["type"] == "book":
            update_book(message)
        elif message["type"] == "fill":
            update_positions(message)
            if time_since(last_convert_time) > TIME_BETWEEN_CONVERT:
                # pass
                # continue
                # convert_ETF()
                convert_ADR()
        elif message["type"] == "trade":
            update_executed(message)
        elif message["type"] == "ack":
            update_positions_from_ack(message)

        if time_since(last_clear_time) > TIME_BETWEEN_CLEAR_BOOKS:
            last_clear_time = time.time()
            clear_books()
        elif time_since(last_trade_time) > TIME_BETWEEN_TRADES:
            last_trade_time = time.time()
            trade_bonds(message)
            trade_adr(message)
            trade_etf(message)



if __name__ == "__main__":
    main()
