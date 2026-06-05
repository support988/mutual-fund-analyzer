import os
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QListWidget, QListWidgetItem, QFileDialog, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from path_utils import get_app_data_path

class FileManagerWidget(QWidget):
    files_changed = pyqtSignal()

    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.config_path = get_app_data_path("config.json")
        self.init_ui()

        self.load_config()

    def init_ui(self):
        layout = QVBoxLayout()

        self.label = QLabel("Drag & Drop CSV files here or use the Browse button")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            "border: 2px dashed #aaa; padding: 20px; color: #111111; "
            "background-color: #ffffff;"
        )
        layout.addWidget(self.label)

        btn_layout = QHBoxLayout()
        self.browse_btn = QPushButton("Browse CSVs")
        self.browse_btn.clicked.connect(self.browse_files)
        btn_layout.addWidget(self.browse_btn)
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        btn_layout.addWidget(self.remove_btn)
        
        layout.addLayout(btn_layout)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        self.setLayout(layout)
        self.setAcceptDrops(True)
        
        # Keep text readable even when the OS/app theme is dark.
        self.setStyleSheet("""
            FileManagerWidget { background-color: #ffffff; }
            QWidget { color: #111111; background-color: #ffffff; }
            QLabel { color: #111111; background-color: #ffffff; }
            QPushButton {
                color: #111111;
                background-color: #e9ecef;
                border: 1px solid #9aa0a6;
                padding: 6px 10px;
            }
            QPushButton:hover { background-color: #dde2e6; }
            QListWidget {
                color: #111111;
                background-color: #ffffff;
                alternate-background-color: #f6f8fa;
                selection-color: #ffffff;
                selection-background-color: #2563eb;
                border: 1px solid #c8ced6;
            }
            QListWidget::item { color: #111111; padding: 4px; }
            QListWidget::item:selected { color: #ffffff; background-color: #2563eb; }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if f.endswith('.csv'):
                self.add_file(f)
        self.save_config()
        self.files_changed.emit()

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select CSV Files", "", "CSV Files (*.csv)")
        for f in files:
            self.add_file(f)
        self.save_config()
        self.files_changed.emit()

    def add_file(self, file_path):
        # Check if already added
        for i in range(self.file_list.count()):
            if self.file_list.item(i).data(Qt.ItemDataRole.UserRole) == file_path:
                return

        fund_name = self.analyzer.add_fund(file_path)
        if fund_name:
            info = self.analyzer.funds[fund_name]
            num_holdings = len(info['df'])
            latest_date = info['dates'][-1].strftime('%d-%b-%y')
            
            display_text = f"{fund_name} | {num_holdings} holdings | Latest: {latest_date}"
            item = QListWidgetItem(display_text)
            item.setForeground(QColor("#111111"))
            item.setBackground(QColor("#ffffff"))
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            item.setData(Qt.ItemDataRole.DisplayRole + 1, fund_name) # Store fund name separately
            self.file_list.addItem(item)

    def remove_selected(self):
        current_item = self.file_list.currentItem()
        if current_item:
            fund_name = current_item.data(Qt.ItemDataRole.DisplayRole + 1)
            self.analyzer.remove_fund(fund_name)
            self.file_list.takeItem(self.file_list.row(current_item))
            self.save_config()
            self.files_changed.emit()

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    paths = json.load(f)
                    for p in paths:
                        if os.path.exists(p):
                            self.add_file(p)
                self.files_changed.emit()
            except:
                pass

    def save_config(self):
        paths = []
        for i in range(self.file_list.count()):
            paths.append(self.file_list.item(i).data(Qt.ItemDataRole.UserRole))
        with open(self.config_path, 'w') as f:
            json.dump(paths, f)
