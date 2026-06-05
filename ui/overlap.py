from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QComboBox, QLabel, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

class OverlapWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Upper: Matrix
        matrix_widget = QWidget()
        matrix_layout = QVBoxLayout(matrix_widget)
        matrix_layout.addWidget(QLabel("Overlap Matrix: C: Count-based | W: Weight-based Overlap"))
        self.matrix_table = QTableWidget()
        self.matrix_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.matrix_table.cellClicked.connect(self.on_matrix_click)
        matrix_layout.addWidget(self.matrix_table)
        splitter.addWidget(matrix_widget)

        # Lower: Comparison (Common Holdings Detail)
        compare_widget = QWidget()
        compare_layout = QVBoxLayout(compare_widget)
        
        sel_layout = QHBoxLayout()
        self.fund1_sel = QComboBox()
        self.fund2_sel = QComboBox()
        self.fund1_sel.currentIndexChanged.connect(self.refresh_comparison)
        self.fund2_sel.currentIndexChanged.connect(self.refresh_comparison)
        
        sel_layout.addWidget(QLabel("<b>Common Holdings Detail:</b> Compare:"))
        sel_layout.addWidget(self.fund1_sel)
        sel_layout.addWidget(QLabel("with"))
        sel_layout.addWidget(self.fund2_sel)
        sel_layout.addStretch()
        compare_layout.addLayout(sel_layout)

        self.compare_table = QTableWidget()
        self.compare_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        compare_layout.addWidget(self.compare_table)
        splitter.addWidget(compare_widget)

        layout.addWidget(splitter)
        self.setLayout(layout)
        
        self.setStyleSheet("""
            OverlapWidget { background-color: white; }
            QWidget { color: black; }
            QHeaderView::section { color: black; background-color: #f0f0f0; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
            QComboBox { color: black; background-color: white; }
        """)

    def refresh_data(self):
        funds = sorted(list(self.analyzer.funds.keys()))
        if not funds: return
        
        self.fund1_sel.blockSignals(True)
        self.fund2_sel.blockSignals(True)
        self.fund1_sel.clear()
        self.fund2_sel.clear()
        self.fund1_sel.addItems(funds)
        self.fund2_sel.addItems(funds)
        if len(funds) > 1:
            self.fund2_sel.setCurrentIndex(1)
        self.fund1_sel.blockSignals(False)
        self.fund2_sel.blockSignals(False)

        # Refresh Matrix
        matrices = self.analyzer.get_overlap_matrix()
        m_count = matrices['count']
        m_weight = matrices['weight']
        
        self.matrix_table.setRowCount(len(m_count))
        self.matrix_table.setColumnCount(len(m_count.columns))
        self.matrix_table.setHorizontalHeaderLabels(m_count.columns)
        self.matrix_table.setVerticalHeaderLabels(m_count.index)

        for i, (idx, row) in enumerate(m_count.iterrows()):
            for j, count_val in enumerate(row):
                weight_val = m_weight.iloc[i, j]
                
                item = QTableWidgetItem(f"C: {count_val:.0f}% | W: {weight_val:.1f}%")
                
                # Weight-based color code: >15% = red, 8-15% = amber, < 8% = green
                if weight_val > 15:
                    bg = QColor("#f8d7da") # light red
                elif weight_val >= 8:
                    bg = QColor("#fff3cd") # light yellow/amber
                else:
                    bg = QColor("#d4edda") # light green
                
                if i == j: bg = QColor("#e2e3e5") # grey for diagonal
                    
                item.setBackground(bg)
                item.setForeground(QColor(0, 0, 0))
                self.matrix_table.setItem(i, j, item)
        
        self.matrix_table.resizeColumnsToContents()
        self.refresh_comparison()

    def on_matrix_click(self, row, col):
        self.fund1_sel.setCurrentIndex(row)
        self.fund2_sel.setCurrentIndex(col)

    def refresh_comparison(self):
        f1 = self.fund1_sel.currentText()
        f2 = self.fund2_sel.currentText()
        if not f1 or not f2:
            return

        df = self.analyzer.get_common_holdings(f1, f2)
        if df.empty:
            self.compare_table.setRowCount(0)
            return

        self.compare_table.setRowCount(len(df))
        self.compare_table.setColumnCount(len(df.columns))
        self.compare_table.setHorizontalHeaderLabels(df.columns)

        for i, (idx, row) in enumerate(df.iterrows()):
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val) if not isinstance(val, float) else f"{val:.2f}")
                item.setForeground(QColor(0, 0, 0))
                self.compare_table.setItem(i, j, item)
        
        self.compare_table.resizeColumnsToContents()
