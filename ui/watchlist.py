import os
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QLineEdit, QLabel, 
                             QHeaderView, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot, QDate
from PyQt6.QtGui import QColor
import price_fetcher
import pandas as pd

class WatchlistWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.watchlist_path = os.path.join(os.getcwd(), "watchlist.json")
        self.watchlist = self.load_watchlist()
        self.init_ui()

    def load_watchlist(self):
        if os.path.exists(self.watchlist_path):
            try:
                with open(self.watchlist_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_watchlist(self):
        try:
            with open(self.watchlist_path, 'w') as f:
                json.dump(self.watchlist, f)
        except Exception as e:
            print(f"Error saving watchlist: {e}")

    def init_ui(self):
        layout = QVBoxLayout()

        # Input row
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Add Stock:"))
        self.stock_input = QLineEdit()
        self.stock_input.setPlaceholderText("Enter stock name as in MF CSV...")
        self.stock_input.returnPressed.connect(self.add_stock)
        input_layout.addWidget(self.stock_input)
        
        self.add_btn = QPushButton("Add to Watchlist")
        self.add_btn.clicked.connect(self.add_stock)
        input_layout.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_stock)
        input_layout.addWidget(self.remove_btn)
        
        self.refresh_btn = QPushButton("Refresh All")
        self.refresh_btn.clicked.connect(self.refresh_data)
        input_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(input_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Stock", "Added Date", "Current Price", "200 EMA", 
            "EMA Status", "MF Alloc Change", "MF Alert"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.setLayout(layout)
        self.setStyleSheet("""
            WatchlistWidget { background-color: white; }
            QWidget { color: black; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
            QPushButton { color: black; background-color: #e1e1e1; border: 1px solid #aaa; padding: 5px; }
        """)

    def add_stock(self):
        name = self.stock_input.text().strip()
        if not name:
            return
        
        if any(item['name'].lower() == name.lower() for item in self.watchlist):
            QMessageBox.information(self, "Exists", "Stock already in watchlist.")
            return
            
        self.watchlist.append({
            'name': name,
            'added_date': QDate.currentDate().toString(Qt.DateFormat.ISODate)
        })
        self.save_watchlist()
        self.stock_input.clear()
        self.refresh_data()

    def remove_stock(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
            
        for row in sorted(rows, reverse=True):
            stock_name = self.table.item(row.row(), 0).text()
            self.watchlist = [item for item in self.watchlist if item['name'] != stock_name]
            
        self.save_watchlist()
        self.refresh_data()

    def refresh_data(self):
        self.table.setRowCount(len(self.watchlist))
        trends = self.analyzer.get_trends()
        
        for i, item in enumerate(self.watchlist):
            name = item['name']
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(item['added_date']))
            
            # Fetch Price Data
            p_data = price_fetcher.get_price_data(name)
            if p_data:
                self.table.setItem(i, 2, QTableWidgetItem(f"{p_data['current_price']:.2f}"))
                self.table.setItem(i, 3, QTableWidgetItem(f"{p_data['ema200']:.2f}"))
                
                status_item = QTableWidgetItem(p_data['ema_status'])
                if "Above 200" in p_data['ema_status']: status_item.setBackground(QColor("#d4edda"))
                elif "Below 200" in p_data['ema_status']: status_item.setBackground(QColor("#f8d7da"))
                self.table.setItem(i, 4, status_item)
            else:
                for col in range(2, 5):
                    self.table.setItem(i, col, QTableWidgetItem("N/A"))

            # MF Alert Logic
            # Check trends for ALL funds
            total_change = 0.0
            is_new = False
            is_exited = False
            
            for fund_name, data in trends.items():
                # check increase/decrease
                inc = data['top_increase']
                if not inc[inc['Name'] == name].empty:
                    total_change += inc[inc['Name'] == name]['Change'].iloc[0]
                
                dec = data['top_decrease']
                if not dec[dec['Name'] == name].empty:
                    total_change += dec[dec['Name'] == name]['Change'].iloc[0]
                    
                # check new/exited
                if not data['new_entries'][data['new_entries']['Name'] == name].empty:
                    is_new = True
                if not data['exited'][data['exited']['Name'] == name].empty:
                    is_exited = True

            change_item = QTableWidgetItem(f"{total_change:+.2f}%")
            if total_change > 0: change_item.setForeground(QColor("green"))
            elif total_change < 0: change_item.setForeground(QColor("red"))
            self.table.setItem(i, 5, change_item)
            
            alert = "Neutral"
            bg = QColor("white")
            if is_new: alert = "New Entry"; bg = QColor("#d1ecf1")
            elif is_exited: alert = "Exited"; bg = QColor("#f8d7da")
            elif total_change > 0.5: alert = "MF Increased"; bg = QColor("#d4edda")
            elif total_change < -0.5: alert = "MF Reduced"; bg = QColor("#fff3cd")
            
            alert_item = QTableWidgetItem(alert)
            alert_item.setBackground(bg)
            self.table.setItem(i, 6, alert_item)
            
        self.table.resizeColumnsToContents()
