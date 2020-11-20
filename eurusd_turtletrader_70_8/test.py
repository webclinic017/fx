import asyncio

from PyQt5.QtWidgets import *

from ib_insync import IB, util
from ib_insync.contract import *

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import pandas

import random

class TickerGraph(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)

        FigureCanvas.__init__(self, fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self,
                QSizePolicy.Expanding,
                QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)

    def plot(self, data):
        self.figure.clf()
        ax = self.figure.add_subplot(111)
        ax.plot(data, 'r-')
        ax.set_title('Data')
        self.draw()

class Window(QWidget):

    def __init__(self, host, port, clientId):
        QWidget.__init__(self)
        self.edit = QLineEdit('', self)
        self.edit.editingFinished.connect(self.add)
        self.connectButton = QPushButton('Connect')
        self.connectButton.clicked.connect(self.onConnectButtonClicked)
        layout = QVBoxLayout(self)
        layout.addWidget(self.edit)
        layout.addWidget(self.connectButton)
        self.graph = TickerGraph(self, width=5, height=4)
        self.graph.move(0,0)
        layout.addWidget(self.graph)
        self.connectInfo = (host, port, clientId)
        self.ib = IB()

    def add(self, text=''):
        text = text #or self.edit.text()
        if text:
            contract = eval(text)
            if (contract and self.ib.qualifyContracts(contract)):
                data = self.ib.reqHistoricalData(
                    contract, endDateTime='', durationStr='30 D',
                    barSizeSetting='4 hours', whatToShow='MIDPOINT', useRTH=True)
                df = util.df(data)
                print(df["close"])
                self.graph.plot(df["close"])
            self.edit.setText(text)

    def onConnectButtonClicked(self, _):
        if self.ib.isConnected():
            self.ib.disconnect()
            self.connectButton.setText('Connect')
        else:
            self.ib.connect(*self.connectInfo)
            self.connectButton.setText('Disconnect')
            self.add(f"Forex('" + str(self.edit.text()) + "')")

    def closeEvent(self, ev):
        asyncio.get_event_loop().stop()


if __name__ == '__main__':
    util.patchAsyncio()
    util.useQt()
    window = Window('127.0.0.1', 7497, 1)
    window.resize(600, 400)
    window.show()
    IB.run()