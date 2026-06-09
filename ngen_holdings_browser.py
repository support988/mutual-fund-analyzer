import sys
import os
import pandas as pd
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, 
    QTreeWidgetItem, QComboBox, QTableWidget, QTableWidgetItem, 
    QLabel, QPushButton, QFrame, QHeaderView, QApplication, 
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QSettings, QUrl
from PyQt6.QtGui import QFont, QColor, QDesktopServices

# Import the data loader logic
from ngen_data_loader import (
    scan_downloads, load_fund_holdings, 
    get_funds_by_category, BASE_DIR
)

# NGEN Holdings Browser
# Version: 1.0.0
# Built for: Altus Family Office
# Last updated: 2024-05-22

class NGENHoldingsBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NGEN Holdings Browser — Altus Family Office")
        self.setMinimumSize(1200, 750)
        
        self.catalog = {}
        self.current_fund = None
        self.settings = QSettings("AltusFamilyOffice", "NGENBrowser")

        self.init_ui()
        self.apply_theme()
        
        # Initial scan and load
        self.refresh_data()
        self.restore_last_state()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- LEFT PANEL: Category Tree ---
        self.left_panel = QFrame()
        self.left_panel.setFixedWidth(260)
        self.left_panel.setObjectName("sidePanel")
        left_layout = QVBoxLayout(self.left_panel)
        
        left_layout.addWidget(QLabel("CATEGORIES"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_category_clicked)
        left_layout.addWidget(self.tree)
        
        main_layout.addWidget(self.left_panel)

        # --- CENTER PANEL: Table and Selection ---
        self.center_panel = QFrame()
        center_layout = QVBoxLayout(self.center_panel)
        
        # Selection Header
        header_layout = QHBoxLayout()
        self.fund_selector = QComboBox()
        self.fund_selector.currentIndexChanged.connect(self.on_fund_selected)
        header_layout.addWidget(QLabel("Select Fund:"))
        header_layout.addWidget(self.fund_selector, 1)
        
        self.resize_btn = QPushButton("Resize Columns")
        self.resize_btn.clicked.connect(self.auto_resize_columns)
        header_layout.addWidget(self.resize_btn)
        
        center_layout.addLayout(header_layout)

        # Info Label
        self.info_label = QLabel("No fund loaded")
        self.info_label.setObjectName("infoLabel")
        center_layout.addWidget(self.info_label)

        # Table
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        center_layout.addWidget(self.table)
        
        main_layout.addWidget(self.center_panel)

        # --- RIGHT PANEL: Summary ---
        self.right_panel = QFrame()
        self.right_panel.setFixedWidth(220)
        self.right_panel.setObjectName("sidePanel")
        right_layout = QVBoxLayout(self.right_panel)

        right_layout.addWidget(QLabel("HOLDINGS SUMMARY"))
        
        self.summary_card = QFrame()
        self.summary_card.setObjectName("summaryCard")
        summary_inner = QVBoxLayout(self.summary_card)
        
        self.lbl_latest_date = QLabel("Latest Date: -")
        self.lbl_total_sec = QLabel("Total Securities: -")
        self.lbl_equity_hold = QLabel("Equity Holdings: -")
        self.lbl_non_equity = QLabel("Non-Equity: -")
        self.lbl_date_range = QLabel("Date Range: -")
        
        for lbl in [self.lbl_latest_date, self.lbl_total_sec, self.lbl_equity_hold, self.lbl_non_equity, self.lbl_date_range]:
            lbl.setWordWrap(True)
            lbl.setObjectName("summaryText")
            summary_inner.addWidget(lbl)
            
        right_layout.addWidget(self.summary_card)
        
        right_layout.addStretch()
        
        # Action Buttons
        self.btn_refresh = QPushButton("Refresh Data")
        self.btn_refresh.clicked.connect(self.refresh_data)
        
        self.btn_open_folder = QPushButton("Open CSV Folder")
        self.btn_open_folder.clicked.connect(self.open_current_folder)
        
        self.btn_open_file = QPushButton("Open CSV File")
        self.btn_open_file.clicked.connect(self.open_current_file)
        
        for btn in [self.btn_refresh, self.btn_open_folder, self.btn_open_file]:
            right_layout.addWidget(btn)

        main_layout.addWidget(self.right_panel)

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Segoe UI', Arial;
            }
            QFrame#sidePanel {
                background-color: #2b2b2b;
                border-radius: 5px;
            }
            QFrame#summaryCard {
                background-color: #1a1a1a;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
            QLabel {
                font-size: 12px;
                color: #aaaaaa;
            }
            QLabel#infoLabel {
                font-size: 14px;
                font-weight: bold;
                color: #00aaff;
                margin-top: 5px;
                margin-bottom: 5px;
            }
            QLabel#summaryText {
                color: #ffffff;
                font-size: 13px;
                margin-bottom: 8px;
            }
            QTreeWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:selected {
                color: #00aaff;
                background-color: #333333;
            }
            QComboBox {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 4px;
                padding: 5px;
                color: white;
            }
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #333333;
                border: 1px solid #333333;
                color: white;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #aaaaaa;
                padding: 5px;
                border: 1px solid #333333;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton#refreshBtn {
                background-color: #00aaff;
            }
        """)

    def refresh_data(self):
        self.catalog = scan_downloads(BASE_DIR)
        self.populate_tree()
        if not self.catalog or not self.catalog.get("Equity"):
            self.info_label.setText("No data found. Run ngen_holdings_history.py first.")

    def populate_tree(self):
        self.tree.clear()
        
        bold_font = QFont()
        bold_font.setBold(True)

        for group, categories in self.catalog.items():
            group_item = QTreeWidgetItem(self.tree)
            group_item.setText(0, group)
            group_item.setFont(0, bold_font)
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            
            for cat_name, fund_list in categories.items():
                cat_item = QTreeWidgetItem(group_item)
                cat_item.setText(0, f"{cat_name} ({len(fund_list)})")
                cat_item.setData(0, Qt.ItemDataRole.UserRole, cat_name)
                
            group_item.setExpanded(True)

    def on_category_clicked(self, item, column):
        cat_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not cat_name:
            return
            
        funds = get_funds_by_category(self.catalog, cat_name)
        
        self.fund_selector.blockSignals(True)
        self.fund_selector.clear()
        for fund in funds:
            self.fund_selector.addItem(fund["fund_name"], fund)
        self.fund_selector.blockSignals(False)
        
        if funds:
            self.fund_selector.setCurrentIndex(0)
            
        self.settings.setValue("last_category", cat_name)

    def on_fund_selected(self, index):
        if index < 0:
            return
        
        fund_dict = self.fund_selector.itemData(index)
        if fund_dict:
            self.current_fund = fund_dict
            self.display_fund(fund_dict)
            self.settings.setValue("last_fund_amfi", fund_dict["amficode"])

    def display_fund(self, fund_dict):
        df = load_fund_holdings(fund_dict["filepath"])
        if df.empty:
            self.info_label.setText("Error loading CSV file.")
            return

        # Update Info Label
        n_sec = len(df)
        n_months = len(df.columns) - 3  # Type, Name, Sector
        self.info_label.setText(f"{fund_dict['fund_name']}  |  {n_sec} securities  |  {n_months} months of data")

        # Update Table
        self.table.clear()
        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns)

        for r_idx, row in df.iterrows():
            is_equity = str(row['Type']).strip().lower() == 'equity'
            
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                
                # Default style
                text_color = QColor("#ffffff")
                
                # Grey out non-equity rows
                if not is_equity:
                    text_color = QColor("#888888")
                
                # Handle "-" cells
                if str(val).strip() == "-":
                    text_color = QColor("#555555")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif c_idx >= 3: # Percentage columns
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                item.setForeground(text_color)
                self.table.setItem(r_idx, c_idx, item)

        self.apply_column_sizing()
        self.update_summary(df)

    def apply_column_sizing(self):
        # Type=120, Name=200, Sector=180, date cols=90
        header = self.table.horizontalHeader()
        if self.table.columnCount() > 0: header.resizeSection(0, 120)
        if self.table.columnCount() > 1: header.resizeSection(1, 200)
        if self.table.columnCount() > 2: header.resizeSection(2, 180)
        for i in range(3, self.table.columnCount()):
            header.resizeSection(i, 90)

    def auto_resize_columns(self):
        self.table.resizeColumnsToContents()

    def update_summary(self, df):
        # Latest Date (first date column)
        date_cols = df.columns[3:]
        latest_date = date_cols[0] if len(date_cols) > 0 else "N/A"
        
        # Security count
        total_sec = len(df)
        
        # Equity Calculation (using latest month)
        equity_df = df[df['Type'].str.strip().lower() == 'equity']
        n_equity = len(equity_df)
        
        if latest_date != "N/A":
            # Convert "-" to 0 for sum
            latest_vals = pd.to_numeric(df[latest_date].replace("-", "0"), errors='coerce').fillna(0)
            equity_vals = pd.to_numeric(equity_df[latest_date].replace("-", "0"), errors='coerce').fillna(0)
            
            total_weight = latest_vals.sum()
            equity_weight = equity_vals.sum()
            
            eq_pct = (equity_weight / total_weight * 100) if total_weight > 0 else 0
            noneq_pct = 100 - eq_pct
        else:
            eq_pct = 0
            noneq_pct = 0

        self.lbl_latest_date.setText(f"Latest Date: {latest_date}")
        self.lbl_total_sec.setText(f"Total Securities: {total_sec}")
        self.lbl_equity_hold.setText(f"Equity Holdings: {n_equity} ({eq_pct:.1f}%)")
        self.lbl_non_equity.setText(f"Non-Equity: {total_sec - n_equity} ({noneq_pct:.1f}%)")
        self.lbl_date_range.setText(f"Date Range: {date_cols[-1]} → {date_cols[0]}" if len(date_cols) > 0 else "Date Range: -")

    def open_current_folder(self):
        if self.current_fund:
            path = os.path.dirname(self.current_fund["filepath"])
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_current_file(self):
        if self.current_fund:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_fund["filepath"]))

    def restore_last_state(self):
        last_cat = self.settings.value("last_category")
        last_amfi = self.settings.value("last_fund_amfi")
        
        if not last_cat:
            # Select first available
            if self.tree.topLevelItemCount() > 0:
                root = self.tree.topLevelItem(0)
                if root and root.childCount() > 0:
                    first_cat = root.child(0)
                    self.on_category_clicked(first_cat, 0)
                    self.tree.setCurrentItem(first_cat)
            return

        # Find and select last category
        if self.tree.topLevelItemCount() > 0:
            root = self.tree.topLevelItem(0)
            for i in range(root.childCount()):
                child = root.child(i)
                if child.data(0, Qt.ItemDataRole.UserRole) == last_cat:
                    self.tree.setCurrentItem(child)
                    self.on_category_clicked(child, 0)
                    
                    # Find and select last fund
                    if last_amfi:
                        for f_idx in range(self.fund_selector.count()):
                            f_data = self.fund_selector.itemData(f_idx)
                            if str(f_data.get("amficode")) == str(last_amfi):
                                self.fund_selector.setCurrentIndex(f_idx)
                                break
                    break

if __name__ == "__main__":
    app = QApplication(sys.argv)
    browser = NGENHoldingsBrowser()
    browser.show()
    sys.exit(app.exec())
