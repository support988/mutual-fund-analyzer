from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, 
                             QTableWidgetItem, QLabel, QSplitter)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import pandas as pd
from PyQt6.QtGui import QColor

class SectorWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
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
            SectorWidget { background-color: white; }
            QWidget { color: black; }
            QHeaderView::section { color: black; background-color: #f0f0f0; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
        """)

    def refresh_data(self):
        df = self.analyzer.get_sector_data()
        if df.empty:
            return

        # Update Chart (Stacked Bar)
        self.ax.clear()
        fund_cols = [c for c in df.columns if c != 'Average']
        df[fund_cols].T.plot(kind='bar', stacked=True, ax=self.ax)
        self.ax.set_title("Sector Exposure by Fund (Latest Month)")
        self.ax.set_ylabel("% Allocation")
        self.ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
        self.figure.tight_layout()
        self.canvas.draw()

        # Update Table
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(df.columns)
        self.table.setVerticalHeaderLabels(df.index)

        for i, (idx, row) in enumerate(df.iterrows()):
            for j, val in enumerate(row):
                item = QTableWidgetItem(f"{val:.2f}%")
                
                # Heatmap coloring for cells
                intensity = int(255 * (1 - min(val / 30, 1))) # Cap at 30% for full intensity
                bg = QColor(intensity, 255, intensity)
                item.setBackground(bg)
                
                # Dynamic contrast
                lum = 0.299 * intensity + 0.587 * 255 + 0.114 * intensity
                item.setForeground(QColor(0, 0, 0) if lum > 140 else QColor(255, 255, 255))
                
                self.table.setItem(i, j, item)
        
        self.table.resizeColumnsToContents()
