from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QLabel, QScrollArea, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

class TrendsWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout()

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Assets:"))
        self.asset_filter = QComboBox()
        self.asset_filter.addItems(["Equity Only", "All Asset Types"])
        self.asset_filter.currentIndexChanged.connect(self.refresh_data)
        filter_layout.addWidget(self.asset_filter)
        filter_layout.addStretch()
        self.main_layout.addLayout(filter_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.scroll.setWidget(self.content_widget)
        
        self.main_layout.addWidget(self.scroll)
        self.setLayout(self.main_layout)
        
        # Force black text color and white background globally for this widget to ensure visibility
        self.setStyleSheet("""
            TrendsWidget { background-color: white; }
            QWidget { color: #111111; background-color: #ffffff; }
            QScrollArea { background-color: #ffffff; border: none; }
            QScrollArea > QWidget > QWidget { background-color: #ffffff; }
            QHeaderView::section {
                color: #111111;
                background-color: #f0f2f4;
                border: 1px solid #c8ced6;
                padding: 4px;
            }
            QTableWidget {
                color: #111111;
                gridline-color: #d0d0d0;
                background-color: #ffffff;
                alternate-background-color: #f6f8fa;
                selection-color: #ffffff;
                selection-background-color: #2563eb;
            }
            QTableWidget::item { color: #111111; background-color: #ffffff; }
            QTableWidget::item:selected { color: #ffffff; background-color: #2563eb; }
            QLabel { color: #111111; background-color: #ffffff; }
            QComboBox {
                color: #111111;
                background-color: #ffffff;
                border: 1px solid #c8ced6;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                color: #111111;
                background-color: #ffffff;
                selection-color: #ffffff;
                selection-background-color: #2563eb;
            }
        """)

    def refresh_data(self):
        # Clear existing
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        asset_filter_val = "Equity" if self.asset_filter.currentText() == "Equity Only" else None
        trends = self.analyzer.get_trends(asset_type_filter=asset_filter_val)
        if not trends:
            self.content_layout.addWidget(QLabel("No trend data available (need at least 2 months)."))
            return

        for fund_name, data in trends.items():
            fund_label = QLabel(f"--- {fund_name} ---")
            fund_label.setStyleSheet(
                "font-weight: bold; font-size: 14px; margin-top: 20px; "
                "color: #111111; background-color: #ffffff;"
            )
            self.content_layout.addWidget(fund_label)

            grid = QHBoxLayout()
            
            # Top Increases
            inc_box = QVBoxLayout()
            inc_box.addWidget(QLabel("Top Increases (3m)"))
            inc_table = self.create_trend_table(data['top_increase'], ['Name', 'Change', 'Latest %'])
            inc_box.addWidget(inc_table)
            grid.addLayout(inc_box)

            # Top Decreases
            dec_box = QVBoxLayout()
            dec_box.addWidget(QLabel("Top Decreases (3m)"))
            dec_table = self.create_trend_table(data['top_decrease'], ['Name', 'Change', 'Latest %'])
            dec_box.addWidget(dec_table)
            grid.addLayout(dec_box)
            
            self.content_layout.addLayout(grid)
            
            grid2 = QHBoxLayout()
            # New Entries
            new_box = QVBoxLayout()
            new_box.addWidget(QLabel("New Entries This Month"))
            new_table = self.create_trend_table(data['new_entries'], ['Name', 'Sector', 'Latest %'])
            new_box.addWidget(new_table)
            grid2.addLayout(new_box)

            # Exited
            exit_box = QVBoxLayout()
            exit_box.addWidget(QLabel("Exited This Month"))
            exit_table = self.create_trend_table(data['exited'], ['Name', 'Sector', 'Prev %'])
            exit_box.addWidget(exit_table)
            grid2.addLayout(exit_box)

            self.content_layout.addLayout(grid2)

    def create_trend_table(self, df, headers):
        table = QTableWidget()
        table.setRowCount(len(df))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setMaximumHeight(200)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet("""
            QTableWidget {
                color: #111111;
                background-color: #ffffff;
                gridline-color: #d0d0d0;
                selection-color: #ffffff;
                selection-background-color: #2563eb;
            }
            QTableWidget::item { color: #111111; background-color: #ffffff; }
            QHeaderView::section {
                color: #111111;
                background-color: #f0f2f4;
                border: 1px solid #c8ced6;
                padding: 4px;
            }
        """)

        for i, (idx, row) in enumerate(df.iterrows()):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val) if not isinstance(val, float) else f"{val:.2f}")
                item.setForeground(QColor(0, 0, 0))
                item.setBackground(QColor(255, 255, 255))
                table.setItem(i, j, item)
        
        table.resizeColumnsToContents()
        return table
