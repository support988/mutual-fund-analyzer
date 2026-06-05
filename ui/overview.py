from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QLineEdit, QComboBox, QCheckBox, QLabel, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

class OverviewWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Filter bar
        filter_layout = QHBoxLayout()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Filter by stock name...")
        self.search_bar.textChanged.connect(self.refresh_data)
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.search_bar)

        self.asset_filter = QComboBox()
        self.asset_filter.addItems(["Equity Only", "All Asset Types"])
        self.asset_filter.currentIndexChanged.connect(self.refresh_data)
        filter_layout.addWidget(QLabel("Assets:"))
        filter_layout.addWidget(self.asset_filter)
        
        self.min_funds = QComboBox()
        self.min_funds.addItems(["All", "2+ Funds", "3+ Funds", "4+ Funds"])
        self.min_funds.currentIndexChanged.connect(self.refresh_data)
        filter_layout.addWidget(QLabel("Min Funds:"))
        filter_layout.addWidget(self.min_funds)

        layout.addLayout(filter_layout)

        # Table
        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        # Enable horizontal scrolling and prevent cutting off
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultSectionSize(120)
        layout.addWidget(self.table)

        self.setLayout(layout)
        
        # Force black text color and white background globally for this widget to ensure visibility
        self.setStyleSheet("""
            OverviewWidget { background-color: white; }
            QWidget { color: black; }
            QHeaderView::section { color: black; background-color: #f0f0f0; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
            QLineEdit, QComboBox { color: black; background-color: white; border: 1px solid #ccc; }
        """)

    def refresh_data(self):
        asset_filter_val = "Equity" if self.asset_filter.currentText() == "Equity Only" else None
        df = self.analyzer.get_master_holdings(asset_type_filter=asset_filter_val)
        
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        # Apply Filters
        search_text = self.search_bar.text().lower()
        if search_text:
            df = df[df['Name'].str.lower().str.contains(search_text, na=False)]
            
        min_f = self.min_funds.currentText()
        if min_f == "2+ Funds":
            df = df[df['Funds Count'] >= 2]
        elif min_f == "3+ Funds":
            df = df[df['Funds Count'] >= 3]
        elif min_f == "4+ Funds":
            df = df[df['Funds Count'] >= 4]

        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(df.columns)

        for i, (idx, row) in enumerate(df.iterrows()):
            fund_count = row['Funds Count']
            bg_color = None
            text_color = QColor(0, 0, 0)
            if fund_count >= 4:
                bg_color = QColor(200, 0, 0) # Strong Red
                text_color = QColor(255, 255, 255) # White text
            elif fund_count == 3:
                bg_color = QColor(255, 140, 0) # Orange
                text_color = QColor(255, 255, 255)
            elif fund_count == 2:
                bg_color = QColor(255, 255, 180) # Light Yellow
                text_color = QColor(0, 0, 0)

            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val) if not isinstance(val, float) else f"{val:.2f}")
                item.setForeground(text_color)
                if bg_color:
                    item.setBackground(bg_color)
                self.table.setItem(i, j, item)
        
        self.table.resizeColumnsToContents()
        # Ensure name column takes space but funds are readable
        if self.table.columnCount() > 0:
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for i in range(1, self.table.columnCount()):
                self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
