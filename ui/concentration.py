from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QComboBox, QLabel, QSplitter, QCompleter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import pandas as pd

class ConcentrationWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Search
        search_layout = QHBoxLayout()
        self.stock_search = QComboBox()
        self.stock_search.setEditable(True)
        self.stock_search.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.stock_search.currentIndexChanged.connect(self.update_chart)
        search_layout.addWidget(QLabel("Select Stock:"))
        search_layout.addWidget(self.stock_search)
        layout.addLayout(search_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Chart
        self.figure, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        splitter.addWidget(self.canvas)

        # Table
        self.table = QTableWidget()
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.table)

        layout.addWidget(splitter)
        self.setLayout(layout)
        
        # Force black text color and white background globally for this widget to ensure visibility
        self.setStyleSheet("""
            ConcentrationWidget { background-color: white; }
            QWidget { color: black; }
            QHeaderView::section { color: black; background-color: #f0f0f0; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
            QComboBox { color: black; background-color: white; border: 1px solid #ccc; }
        """)

    def refresh_data(self):
        # Update autocomplete list
        latest_df = self.analyzer.get_master_holdings(asset_type_filter=None)
        if latest_df.empty or 'Name' not in latest_df.columns:
            self.stock_search.blockSignals(True)
            self.stock_search.clear()
            self.stock_search.blockSignals(False)
            self.ax.clear()
            self.canvas.draw()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        stocks = sorted(latest_df['Name'].unique().tolist())
        self.stock_search.blockSignals(True)
        self.stock_search.clear()
        self.stock_search.addItems(stocks)
        self.stock_search.blockSignals(False)
        self.update_chart()

    def update_chart(self):
        stock_name = self.stock_search.currentText()
        if not stock_name:
            return

        df = self.analyzer.get_stock_time_series(stock_name)
        if df.empty:
            return

        self.ax.clear()
        
        # Plot each fund
        fund_cols = [c for c in df.columns if c not in ['Date', 'AVERAGE']]
        for fund in fund_cols:
            self.ax.plot(df['Date'], df[fund], label=fund, alpha=0.6, marker='o', markersize=4)
        
        # Plot Average bold
        self.ax.plot(df['Date'], df['AVERAGE'], label='AVERAGE', linewidth=3, color='black', marker='s')
        
        self.ax.set_title(f"Allocation Trend: {stock_name}")
        self.ax.set_ylabel("% Allocation")
        self.ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        self.figure.tight_layout()
        self.canvas.draw()

        # Update Table
        # Rows = funds + sum + avg
        # Cols = dates
        table_df = df.set_index('Date').T
        self.table.setRowCount(len(table_df))
        self.table.setColumnCount(len(table_df.columns))
        
        col_labels = [d.strftime('%b-%y') for d in table_df.columns]
        self.table.setHorizontalHeaderLabels(col_labels)
        self.table.setVerticalHeaderLabels(table_df.index)

        for i, (idx, row) in enumerate(table_df.iterrows()):
            for j, val in enumerate(row):
                item = QTableWidgetItem(f"{val:.2f}" if val > 0 else "-")
                item.setForeground(QColor(0, 0, 0))
                
                # Badges logic (simplified for table)
                # "New Entry" if current > 0 and previous == 0
                if j > 0:
                    prev_val = row.iloc[j-1]
                    if val > 0 and prev_val == 0:
                        item.setToolTip("New Entry")
                        item.setForeground(QColor(0, 150, 0))
                    elif val == 0 and prev_val > 0:
                        item.setText("EXITED")
                        item.setForeground(QColor(200, 0, 0))
                
                self.table.setItem(i, j, item)
        
        self.table.resizeColumnsToContents()
