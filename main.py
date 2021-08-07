#!/usr/bin/python
# ~~~~~==============   HOW TO RUN   ==============~~~~~
# 1) Configure things in CONFIGURATION section
# 2) Change permissions: chmod +x bot.py
# 3) Run in loop: while true; do ./bot.py; sleep 1; done

from __future__ import print_function

import sys
import socket
import json

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

order_count = 0
positions = {"VALBZ": {"buy": 0, "sell": 10000}, "VALE": {"buy": 0, "sell": 10000}}



def do_order(symbol, dir, price, size):
    global order_count
    write_to_exchange(exchange, {"type": "add", "order_id": order_count, "symbol": symbol, "dir": dir, "price": price, "size": size})
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
    pass

def update_adr(message):
    if message["symbol"] == "VALBZ":
        pass
    else: 
        pass



def trade_etf(message):
    pass

    





def main():
    global exchange
    global positions
    exchange = connect()
    write_to_exchange(exchange, {"type": "hello", "team": team_name.upper()})
    hello_from_exchange = read_from_exchange(exchange)
    # A common mistake people make is to call write_to_exchange() > 1
    # time for every read_from_exchange() response.
    # Since many write messages generate marketdata, this will cause an
    # exponential explosion in pending messages. Please, don't do that!
    print("The exchange replied:", hello_from_exchange, file=sys.stderr)
    while True:
        message = read_from_exchange(exchange)
        if message["type"] == "close":
            print("The round has ended")
            break
        elif message["type"] == "book":
            if message["symbol"] == "BOND":
                trade_bonds(message)
            elif message["symbol"] == "VALBZ" or message["symbol"] == "VALE":
                trade_adr(message)
            else:
                trade_etf(message)
        else:
            




if __name__ == "__main__":
    main()
