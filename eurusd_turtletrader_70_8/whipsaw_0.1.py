#####################################################
import datetime
from ib_insync import *
from ibapi import *
import logging
import pytz
import sys
import pandas as pd
import pandas_ta as ta

#####################################################
# Algorithmic strategy class for interactive brokers:
class IBAlgoStrategy(object):
    """
    Algorithmic trading strategy for Interactive Brokers
    """

    def __init__(self):
        """Initialize Algorithm"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.handler = logging.FileHandler('IBKRTradingAlgorithm.log')
        self.handler.setLevel(logging.INFO)
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.handler.setFormatter(self.formatter)
        self.logger.addHandler(self.handler)
        self.logger.info('Starting log at {}'.format(datetime.datetime.now()))

        # Connect to IB
        self.ib = self.connect()

        # Create empty list of instruments
        self.instruments = []

        # Run main loop
        self.run()

#####################################################
    def run(self):
        """Run logic for today's trading"""
        self.log()
        start_time = datetime.datetime.now(tz=pytz.timezone('Asia/Shanghai'))
        self.log('Beginning to run trading algorithm at {} HKT'
                 .format(start_time))

        for instrument in self.instruments:

            # Initial Variable Setup
            indicators = self.get_indicators(instrument)

            open_parents = []
            open_children = []
            for o in self.get_open_trades(instrument):
                if o.order.parentId == 0:
                    open_parents.append(o)
                else:
                    open_children.append(o)

            open_parent_count = len(open_parents)
            cash_balance = self.get_cash_balance(instrument)
            unit_full = True
            is_long = False
            is_short = False

            max_unit_size = 0
            for v in self.ib.accountSummary():
                if v.currency == 'BASE' and v.tag == 'CashBalance':
                    max_unit_size = float(v.value) * float(0.02)
                    self.log('BASE CURRENCY VALUE: {}'.format(v))

            if cash_balance > float(100):
                is_long = True

            if cash_balance < float(-100):
                is_short = True

            self.log("Unit size for {}: {}. 2p of funds: {}".format(instrument.localSymbol, self.get_cash_balance(instrument) * self.get_usd_exchange(instrument), max_unit_size))
            if abs(self.get_cash_balance(instrument) * self.get_usd_exchange(instrument)) < \
               max_unit_size:
                if is_long or is_short:
                    unit_full = False

            self.log("Is the unit full for {}? {}".format(instrument.localSymbol, unit_full))

            # Purge outdated/uneeded open orders:
            self.clean_orders(instrument)

            # If not long or short, place initial entry orders:
            if cash_balance < 100 and cash_balance > -100:
                self.place_initial_entry_orders(instrument, indicators)

            # If there is a unit that is not full:
            if not unit_full:
                self.log('Checking if long or short for {}...'
                         .format(instrument.localSymbol))

                if abs(self.get_cash_balance(instrument) * self.get_usd_exchange(instrument)) < \
                   max_unit_size * float(0.25):
                    i = 1
                elif abs(self.get_cash_balance(instrument) * self.get_usd_exchange(instrument)) < \
                        max_unit_size * float(0.5):
                    i = 2
                elif abs(self.get_cash_balance(instrument) * self.get_usd_exchange(instrument)) < \
                        max_unit_size * float(0.75):
                    i = 3
                else:
                    i = 4

                self.log("For instrument {}, i={}".format(instrument.localSymbol, i))

                # If long (>100 units), place compound long orders:
                if is_long:
                    self.log('Currently long on {}. Placing compound orders.'
                             .format(instrument.localSymbol))
                    while i < 4:
                        for o in self.go_long(instrument,
                                              indicators,
                                              offset=i,
                                              is_compound_order=True):
                            self.ib.placeOrder(instrument, o)
                            self.ib.sleep(1)
                        i += 1
                    self.log('Placed {} long compound orders on {}.'
                             .format(i, instrument.localSymbol))

                # If short (<-100 units), place compound short orders:
                elif is_short:
                    self.log('Currently short on {}. Placing compound orders.'
                             .format(instrument.localSymbol))
                    while i < 4:
                        for o in self.go_short(instrument,
                                               indicators,
                                               total_quantity=cash_balance,
                                               offset=i,
                                               is_compound_order=True):
                            self.ib.placeOrder(instrument, o)
                            self.ib.sleep(1)
                        i += 1
                    self.log('Placed {} short compound orders on {}.'
                             .format(i, instrument.localSymbol))

            if is_long:
                # Place exit order for complete unit (all completed orders)
                self.log("Placing long exit order for complete {} unit"
                         .format(instrument.localSymbol))
                for o in self.go_long(instrument,
                                      indicators,
                                      total_quantity=cash_balance,
                                      is_exit_all=True):
                    self.ib.placeOrder(instrument, o)
            elif is_short:
                # Place exit order for complete unit (all completed orders)
                self.log("Placing short exit order for complete {} unit"
                         .format(instrument.localSymbol))
                for o in self.go_short(instrument,
                                       indicators,
                                       total_quantity=cash_balance,
                                       is_exit_all=True):
                    self.ib.placeOrder(instrument, o)

####################################################
    def connect(self):
        """Connect to Interactive Brokers TWS"""

        self.log('Connecting to Interactive Brokers TWS...')
        try:
            ib = IB()
            ib.connect('127.0.0.1', 7497, clientId=0)
            ib.reqAutoOpenOrders(True)
            # Requesting manual pending orders doesn't work with this:            
            # ib.connect('127.0.0.1', 7497, clientId=1)
            self.log('Connected')
            self.log()
            return ib
        except:
            self.log('Error in connecting to TWS!! Exiting...')
            self.log(sys.exc_info()[0])
            exit(-1)

#####################################################
    def log(self, msg=""):
        """Add log to output file"""
        self.logger.info(msg)
        print(msg)

#####################################################
    def clean_orders(self, instrument):
        """Cleans orders based on strategy"""

        orders = self.get_open_trades(instrument)

        replaced_sl_prices = []

        for o in orders:
            if o.order.parentId == "" and "compound" in o.order.orderRef:
                self.ib.cancelOrder(o.order)

        for o in orders:
            if "sl" in o.order.orderRef:
                self.log("Replaced sl prices {}".format(replaced_sl_prices))
                self.log("current sl order price: {}".format(o.order.conditions[0].price))
            if "sl" in o.order.orderRef and o.order.conditions[0].price not in replaced_sl_prices:
                self.log("Placing NEW STOP!!!")
                replaced_sl_prices.append(o.order.conditions[0].price)
                self.ib.placeOrder(instrument,
                                   self.place_order(instrument,
                                                    self.ib.client.getReqId(),
                                                    action=o.order.action,
                                                    order_type=o.order.orderType,
                                                    tif=o.order.tif,
                                                    total_quantity=o.order.totalQuantity,
                                                    transmit=o.order.transmit,
                                                    price_condition=o.order.conditions[0].price,
                                                    order_ref=instrument.localSymbol + "_sl_" + str(o.order.orderRef)[-2:-1],
                                                    is_more=o.order.conditions[0].isMore))

        # Cancel all extra entry/exit orders
        # (exit to be replaced later in self.run),
        # and orders without a proper order reference
        for o in orders:
            self.ib.cancelOrder(o.order)

#####################################################
    def get_open_trades(self, instrument):
        """Returns the number of unfilled trades open for a currency"""
        orders = []
        self.ib.sleep(1)
        for t in self.ib.openTrades():
            if t.contract.localSymbol == instrument.localSymbol:
                orders.append(t)
                # self.log('Found order for instrument {}: {} {}'
                #          .format(instrument.localSymbol,
                #                  t.order.action,
                #                 t.order.totalQuantity))
        order_count = len(orders)
        self.log('Currently in {} open orders for instrument {}.'
                 .format(order_count, instrument.localSymbol))
        return orders

#####################################################
    def add_instrument(self, instrument_type, ticker,
                       symbol, currency, exchange='IDEALPRO'):
        """Adds instrument as an IB contract to instruments list"""
        self.log("Adding instrument {}".format(ticker))

        if instrument_type == 'Forex':
            instrument = Forex(ticker, exchange=exchange,
                               symbol=symbol, currency=currency)
        else:
            raise ValueError(
                       "Invalid instrument type: {}".format(instrument_type))

        self.ib.qualifyContracts(instrument)
        self.instruments.append(instrument)

#####################################################
    def get_available_funds(self):
        """Returns available funds in USD"""
        account_values = self.ib.accountValues()
        available_funds = 0
        i = 0
        for value in account_values:
            if account_values[i].tag == 'AvailableFunds':
                available_funds = float(account_values[i].value)
                break
            i += 1
        self.log('Available funds: {} {}'.format(available_funds,
                                                 account_values[i].currency))
        return available_funds

#####################################################
    def get_cash_balance(self, instrument):
        """Returns current position for currency pair in units"""
        account_values = self.ib.accountValues()
        cash_balance = 0
        i = 0
        for value in account_values:
            if account_values[i].tag == 'CashBalance' and \
               account_values[i].currency == instrument.localSymbol[0:3]:
                cash_balance = float(account_values[i].value)
                break
            i += 1
        self.log("Current {} cash balance: {} units"
                 .format(instrument.localSymbol[0:3], cash_balance))
        return cash_balance

#####################################################
    def get_usd_exchange(self, instrument):
        """Get the exchange rate between currency and USD"""
        assert (instrument.localSymbol in ['GBP.JPY', 'AUD.CAD', 'EUR.USD']), \
               'Invalid Currency!'

        if instrument.localSymbol == 'GBP.JPY':
            ticker = self.ib.reqMktData(contract=Forex(pair='USDJPY',
                                                       symbol='USD',
                                                       currency='JPY'))
            self.ib.sleep(1)
            return 1 / ticker.marketPrice()
        elif instrument.localSymbol == 'AUD.CAD':
            ticker = self.ib.reqMktData(contract=Forex(pair='USDCAD',
                                                       symbol='USD',
                                                       currency='CAD'))
            self.ib.sleep(1)
            return 1 / ticker.marketPrice()
        elif instrument.localSymbol == 'EUR.USD':
            return 1

#####################################################
    def set_position_size(self, instrument, indicators, sl_size):
        """Sets position size in USD based on available funds and volitility"""
        position_size = 0

        # Get position size in USD
        available_funds = self.get_available_funds()
        equity_at_risk = available_funds * 0.005
        # size_in_usd = int(round(equity_at_risk / sl_size, 2))

        # Get position size as units of symbol
        if instrument.localSymbol == 'EUR.USD':
            position_size = round(equity_at_risk / sl_size)
        elif instrument.localSymbol == 'GBP.JPY':
            ticker = self.ib.reqMktData(contract=Forex(pair='USDJPY',
                                                       symbol='USD',
                                                       currency='JPY'))
            self.ib.sleep(1)
            try:
                position_size = round(ticker.marketPrice()
                                      * equity_at_risk
                                      / sl_size)
            except:
                ValueError("Inappropriate ticker price returned. \
                            Cannot calculate position size!")
        elif instrument.localSymbol == 'AUD.CAD':
            ticker = self.ib.reqMktData(contract=Forex(pair='USDCAD',
                                                       symbol='USD',
                                                       currency='CAD'))
            self.ib.sleep(1)
            try:
                position_size = round(ticker.marketPrice()
                                      * equity_at_risk
                                      / sl_size)
            except:
                ValueError("Inappropriate ticker price returned. \
                            Cannot calculate position size!")
        else:
            self.log('Invalid instrument {}! Could not calculate position size.'
                     .format(instrument.localSymbol))
            return None
        return position_size

#####################################################
    def get_atr_multiple(self, instrument, indicators, multiplier=0.5):
        """Sets absolute value of SL equal to 1/2 ATR"""
        indicators = self.get_indicators(instrument)
        volatility = indicators['atr'][(indicators.axes[0].stop - 1)]
        sl_size = self.adjust_for_price_increments(instrument,
                                                   multiplier * volatility)
        # self.log('Current ATR={}, sl={}'.format(volatility, sl_size))
        return sl_size

#####################################################
    def adjust_for_price_increments(self, instrument, value):
        """Adjust given value for instrument's allowed price increments."""
        increment = None
        if instrument.localSymbol == 'EUR.USD':
            increment = 0.00005
        elif instrument.localSymbol == 'GBP.JPY':
            increment = 0.005
        elif instrument.localSymbol == 'AUD.CAD':
            increment = 0.00005
        else:
            self.log('Invalid pair! Cannot calculate SL!')
            return None
        value = increment * round(value / increment)
        return value

#####################################################
    def go_short(self, instrument, indicators, *args, **kwargs):
        """Place short order according to strategy with an offset from LTL"""
        offset = kwargs.get('offset', 0)
        is_exit_all = kwargs.get('is_exit_all', False)
        is_compound_order = kwargs.get('is_compound_order', False)
        sl_size = kwargs.get('sl_size',
                             self.get_atr_multiple(instrument, indicators))
        total_quantity = kwargs.get('total_quantity',
                                    self.set_position_size(instrument,
                                                           indicators,
                                                           sl_size))
        long_term_low = self.adjust_for_price_increments(instrument,
                                                         indicators
                                                         ['long_dcl']
                                                         [(indicators.axes[0]
                                                           .stop - 1)]) \
            - offset * self.get_atr_multiple(instrument, indicators)
        short_exit_condition = self.adjust_for_price_increments(instrument,
                                                                indicators
                                                                ['short_dcu']
                                                                [(indicators
                                                                 .axes[0]
                                                                 .stop - 1)]) \
            - offset * self.get_atr_multiple(instrument, indicators)

        orders = []

        if is_exit_all:
            orders.append(self.place_order(instrument,
                          self.ib.client.getReqId(),
                          action="BUY",
                          order_type="MKT",
                          tif="GTC",
                          total_quantity=total_quantity,
                          transmit=True,
                          price_condition=short_exit_condition,
                          is_more=True,
                          order_ref=str(instrument.localSymbol +
                                        "_short_exit_all")))
            return orders

        compound_order_ref = ""

        if is_compound_order:
            compound_order_ref = "_compound"

        short_entry_a = self.place_order(instrument=instrument,
                                         order_id=self.ib.client.getReqId(),
                                         action="SELL",
                                         order_type="MKT",
                                         total_quantity=total_quantity,
                                         transmit=False,
                                         price_condition=long_term_low,
                                         is_more=False,
                                         order_ref=str(instrument.localSymbol + compound_order_ref + "_short_entry_a"))

        short_sl_a = self.place_order(instrument=instrument,
                                      order_id=self.ib.client.getReqId(),
                                      action="BUY",
                                      order_type="MKT",
                                      total_quantity=total_quantity,
                                      transmit=False,
                                      parent_id=short_entry_a.orderId,
                                      price_condition=long_term_low + sl_size,
                                      is_more=True,
                                      order_ref=str(instrument.localSymbol + compound_order_ref + "_short_sl_a"))
        short_exit_a = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=False,
                                        parent_id=short_entry_a.orderId,
                                        price_condition=short_exit_condition,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_short_exit_a"))

        short_entry_b = self.place_order(instrument=instrument,
                                         order_id=self.ib.client.getReqId(),
                                         action="SELL",
                                         order_type="MKT",
                                         total_quantity=total_quantity,
                                         transmit=False,
                                         parent_id=short_sl_a.orderId,
                                         price_condition=long_term_low,
                                         is_more=False,
                                         order_ref=str(instrument.localSymbol + compound_order_ref + "_short_entry_b"))
        short_sl_b = self.place_order(instrument=instrument,
                                      order_id=self.ib.client.getReqId(),
                                      action="BUY",
                                      order_type="MKT",
                                      total_quantity=total_quantity,
                                      transmit=False,
                                      parent_id=short_entry_b.orderId,
                                      price_condition=long_term_low + sl_size,
                                      is_more=True,
                                      order_ref=str(instrument.localSymbol + compound_order_ref + "_short_sl_b"))
        short_exit_b = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=False,
                                        parent_id=short_entry_b.orderId,
                                        price_condition=short_exit_condition,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_short_exit_b"))

        short_entry_c = self.place_order(instrument=instrument,
                                         order_id=self.ib.client.getReqId(),
                                         action="SELL",
                                         order_type="MKT",
                                         total_quantity=total_quantity,
                                         transmit=False,
                                         parent_id=short_sl_b.orderId,
                                         price_condition=long_term_low,
                                         is_more=False,
                                         order_ref=str(instrument.localSymbol + compound_order_ref + "_short_entry_c"))
        short_sl_c = self.place_order(instrument=instrument,
                                      order_id=self.ib.client.getReqId(),
                                      action="BUY",
                                      order_type="MKT",
                                      total_quantity=total_quantity,
                                      transmit=False,
                                      parent_id=short_entry_c.orderId,
                                      price_condition=long_term_low + sl_size,
                                      is_more=True,
                                      order_ref=str(instrument.localSymbol + compound_order_ref + "_short_sl_c"))
        short_exit_c = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=True,
                                        parent_id=short_entry_c.orderId,
                                        price_condition=short_exit_condition,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_short_exit_c"))

        orders = [short_entry_a,
                  short_sl_a,
                  short_exit_a,
                  short_entry_b,
                  short_sl_b,
                  short_exit_b,
                  short_entry_c,
                  short_sl_c,
                  short_exit_c]
        return orders

#####################################################
    def place_stop_for_filled_trade(self, instrument, trade, indicators):
        """Place stop for a trade that has already been filled"""
        total_quantity = trade.order.totalQuantity

#####################################################
    def go_long(self, instrument, indicators, *args, **kwargs):
        """Place long order according to strategy with an offset from LTH"""
        offset = kwargs.get('offset', 0)
        sl_size = kwargs.get('sl_size',
                             self.get_atr_multiple(instrument, indicators))
        is_exit_all = kwargs.get('is_exit_all', False)
        is_compound_order = kwargs.get('is_compound_order', False)
        total_quantity = kwargs.get('total_quantity',
                                    self.set_position_size(instrument,
                                                           indicators,
                                                           sl_size))
        long_term_high = self.adjust_for_price_increments(instrument,
                                                          indicators
                                                          ['long_dcu']
                                                          [(indicators.axes[0]
                                                            .stop - 1)]) \
            + offset * self.get_atr_multiple(instrument, indicators)
        long_exit_condition = self.adjust_for_price_increments(instrument,
                                                               indicators
                                                               ['short_dcl']
                                                               [(indicators
                                                                .axes[0]
                                                                .stop - 1)]) \
            + offset * self.get_atr_multiple(instrument, indicators)

        orders = []

        if is_exit_all:
            self.log("Placing exit order for complete unit! Parameters:")
            self.log("Total quantity = {}, \
                     price condition = {}, order ref = {}"
                     .format(total_quantity,
                             long_exit_condition,
                             str(instrument.localSymbol +
                                 "_long_exit_all")))
            orders.append(self.place_order(instrument,
                          self.ib.client.getReqId(),
                          action="SELL",
                          order_type="MKT",
                          tif="GTC",
                          total_quantity=total_quantity,
                          transmit=True,
                          is_more=False,
                          price_condition=long_exit_condition,
                          order_ref=str(instrument.localSymbol +
                                        "_long_exit_all")))
            return orders

        compound_order_ref = ""

        if is_compound_order:
            compound_order_ref = "_compound"

        long_entry_a = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=False,
                                        price_condition=long_term_high,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_long_entry_a"))
        long_sl_a = self.place_order(instrument=instrument,
                                     order_id=self.ib.client.getReqId(),
                                     action="SELL",
                                     order_type="MKT",
                                     total_quantity=total_quantity,
                                     transmit=False,
                                     parent_id=long_entry_a.orderId,
                                     price_condition=long_term_high - sl_size,
                                     is_more=False,
                                     order_ref=str(instrument.localSymbol + compound_order_ref + "_long_sl_a"))
        long_exit_a = self.place_order(instrument=instrument,
                                       order_id=self.ib.client.getReqId(),
                                       action="SELL",
                                       order_type="MKT",
                                       total_quantity=total_quantity,
                                       transmit=False,
                                       parent_id=long_entry_a.orderId,
                                       price_condition=long_exit_condition,
                                       is_more=False,
                                       order_ref=str(instrument.localSymbol + compound_order_ref + "_long_exit_a"))

        long_entry_b = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=False,
                                        parent_id=long_sl_a.orderId,
                                        price_condition=long_term_high,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_long_entry_b"))
        long_sl_b = self.place_order(instrument=instrument,
                                     order_id=self.ib.client.getReqId(),
                                     action="SELL",
                                     order_type="MKT",
                                     total_quantity=total_quantity,
                                     transmit=False,
                                     parent_id=long_entry_b.orderId,
                                     price_condition=long_term_high - sl_size,
                                     is_more=False,
                                     order_ref=str(instrument.localSymbol + compound_order_ref + "_long_sl_b"))
        long_exit_b = self.place_order(instrument=instrument,
                                       order_id=self.ib.client.getReqId(),
                                       action="SELL",
                                       order_type="MKT",
                                       total_quantity=total_quantity,
                                       transmit=False,
                                       parent_id=long_entry_b.orderId,
                                       price_condition=long_exit_condition,
                                       is_more=False,
                                       order_ref=str(instrument.localSymbol + compound_order_ref + "_long_exit_b"))

        long_entry_c = self.place_order(instrument=instrument,
                                        order_id=self.ib.client.getReqId(),
                                        action="BUY",
                                        order_type="MKT",
                                        total_quantity=total_quantity,
                                        transmit=False,
                                        parent_id=long_sl_b.orderId,
                                        price_condition=long_term_high,
                                        is_more=True,
                                        order_ref=str(instrument.localSymbol + compound_order_ref + "_long_entry_c"))
        long_sl_c = self.place_order(instrument=instrument,
                                     order_id=self.ib.client.getReqId(),
                                     action="SELL",
                                     order_type="MKT",
                                     total_quantity=total_quantity,
                                     transmit=False,
                                     parent_id=long_entry_c.orderId,
                                     price_condition=long_term_high - sl_size,
                                     is_more=False,
                                     order_ref=str(instrument.localSymbol + compound_order_ref + "_long_sl_c"))
        long_exit_c = self.place_order(instrument=instrument,
                                       order_id=self.ib.client.getReqId(),
                                       action="SELL",
                                       order_type="MKT",
                                       total_quantity=total_quantity,
                                       transmit=True,
                                       parent_id=long_entry_c.orderId,
                                       price_condition=long_exit_condition,
                                       is_more=False,
                                       order_ref=str(instrument.localSymbol + compound_order_ref + "_long_exit_c"))

        orders = [long_entry_a,
                  long_sl_a,
                  long_exit_a,
                  long_entry_b,
                  long_sl_b,
                  long_exit_b,
                  long_entry_c,
                  long_sl_c,
                  long_exit_c]
        return orders

#####################################################
    def place_initial_entry_orders(self, instrument, indicators):
        """Initial entry"""
        sl_size = self.get_atr_multiple(instrument, indicators)
        total_quantity = self.set_position_size(instrument,
                                                indicators,
                                                sl_size)

        self.log("Placing long initial orders for instrument {}"
                 .format(instrument.localSymbol))
        long_entry_attempts = self.go_long(instrument,
                                           indicators,
                                           sl_size=sl_size,
                                           total_quantity=total_quantity)

        self.log("Placing short initial orders for instrument {}"
                 .format(instrument.localSymbol))
        short_entry_attempts = self.go_short(instrument,
                                             indicators,
                                             sl_size=sl_size,
                                             total_quantity=total_quantity)

        self.ib.oneCancelsAll(orders=[long_entry_attempts[0],
                                      short_entry_attempts[0]],
                              ocaGroup="OCA_"
                              + str(instrument.localSymbol)
                              + str(self.ib.client.getReqId()),
                              ocaType=1)

        orders = []
        for o in long_entry_attempts:
            orders.append(o)
        for o in short_entry_attempts:
            orders.append(o)

        for o in orders:
            self.ib.placeOrder(instrument, o)
            self.ib.sleep(1)

#####################################################
    def place_order(self,
                    instrument,
                    order_id,
                    action,
                    order_type,
                    tif="GTC",
                    total_quantity=0,
                    transmit=False,
                    *args, **kwargs):
        is_more = kwargs.get('is_more', "ERROR")
        price_condition = kwargs.get('price_condition', "ERROR")
        parent_id = kwargs.get('parent_id', "ERROR")
        order_ref = kwargs.get('order_ref', "ERROR")

        order = Order()
        order.orderId = order_id
        order.action = action
        order.orderType = order_type
        order.totalQuantity = total_quantity
        order.transmit = transmit
        order.tif = tif
        if parent_id != "ERROR":
            order.parentId = parent_id

        if order_ref != "ERROR":
            order.orderRef = order_ref

        if price_condition != "ERROR" and is_more != "ERROR":
            order.conditions = [PriceCondition(conId = instrument.conId,
                                               exch='IDEALPRO',
                                               isMore=is_more,
                                               price=price_condition)]

        return order

#####################################################
    def get_indicators(self, instrument):
        bars = self.ib.reqHistoricalData(contract=instrument,
                                         endDateTime='',
                                         durationStr='6 M',
                                         barSizeSetting='1 day',
                                         whatToShow='MIDPOINT',
                                         useRTH=True)
        df = pd.DataFrame(bars)
        del df['volume']
        del df['barCount']
        del df['average']
        atr = pd.DataFrame(ta.atr(high=df['high'],
                           low=df['low'],
                           close=df['close'],
                           length=20))
        long_donchian = pd.DataFrame(ta.donchian(high=df['high'],
                                                 low=df['low'],
                                                 upper_length=70,
                                                 lower_length=70))
        short_donchian = pd.DataFrame(ta.donchian(high=df['high'],
                                                  low=df['low'],
                                                  upper_length=8,
                                                  lower_length=8))
        df = pd.concat([df, atr, long_donchian, short_donchian],
                       axis=1,
                       join="outer")
        df.columns.values[5] = 'atr'
        df.columns.values[6] = 'long_dcl'
        df.columns.values[7] = 'long_dcm'
        df.columns.values[8] = 'long_dcu'
        df.columns.values[9] = 'short_dcl'
        df.columns.values[10] = 'short_dcm'
        df.columns.values[11] = 'short_dcu'
        # self.log(df.tail())
        return df

#####################################################
# MAIN PROGRAMME:
if __name__ == '__main__':
    # Create algo object
    algo = IBAlgoStrategy()

    # Add instruments to trade
    algo.add_instrument('Forex', ticker='GBPJPY', symbol='GBP', currency='JPY')
    algo.add_instrument('Forex', ticker='EURUSD', symbol='EUR', currency='USD')
    algo.add_instrument('Forex', ticker='AUDCAD', symbol='AUD', currency='CAD')

    # Run for the day
    algo.run()