import sys
import os
import traceback

# Force absolute path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, 
                                 QVBoxLayout, QWidget, QPushButton, QFileDialog, QMessageBox,
                                 QTextEdit, QSplitter, QHBoxLayout, QLabel)
from PyQt6.QtCore import QObject, pyqtSignal, Qt, pyqtSlot, QDateTime

from analyzer import MFAnalyzer
from ui.file_manager import FileManagerWidget
from ui.overview import OverviewWidget
from ui.overlap import OverlapWidget
from ui.concentration import ConcentrationWidget
from ui.sector import SectorWidget
from ui.trends import TrendsWidget
from ui.prospects import ProspectsWidget
from ui.watchlist import WatchlistWidget
from exporter import export_to_excel
import price_fetcher

class LogStream(QObject):
    new_log = pyqtSignal(str)
    def write(self, text):
        self.new_log.emit(str(text))
    def flush(self):
        pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mutual Fund Portfolio Overlap & Concentration Tracker")
        self.resize(1200, 800)

        self.analyzer = MFAnalyzer()
        
        # Log redirection
        self.log_stream = LogStream()
        self.log_stream.new_log.connect(self.append_log)
        sys.stdout = self.log_stream
        sys.stderr = self.log_stream
        
        self.init_ui()
        print("Application Started - Log Console Initialized")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)

        self.export_btn = QPushButton("Export to Excel (.xlsx)")
        self.export_btn.clicked.connect(self.export_data)
        left_layout.addWidget(self.export_btn)

        self.tabs = QTabWidget()
        
        self.file_manager = FileManagerWidget(self.analyzer)
        self.overview = OverviewWidget(self.analyzer)
        self.overlap = OverlapWidget(self.analyzer)
        self.concentration = ConcentrationWidget(self.analyzer)
        self.sector = SectorWidget(self.analyzer)
        self.trends = TrendsWidget(self.analyzer)
        self.prospects = ProspectsWidget(self.analyzer)
        self.watchlist = WatchlistWidget(self.analyzer)

        self.tabs.addTab(self.file_manager, "File Management")
        self.tabs.addTab(self.overview, "Portfolio Overview")
        self.tabs.addTab(self.overlap, "Overlap Analysis")
        self.tabs.addTab(self.concentration, "Concentration Tracker")
        self.tabs.addTab(self.sector, "Sector Breakdown")
        self.tabs.addTab(self.trends, "Trend Analysis")
        self.tabs.addTab(self.prospects, "Investment Prospects")
        self.tabs.addTab(self.watchlist, "Watchlist")

        left_layout.addWidget(self.tabs)
        self.splitter.addWidget(left_container)

        # Right side: Log Console
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.addWidget(QLabel("<b>Log Console</b>"))
        
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; font-size: 9pt;")
        right_layout.addWidget(self.log_console)
        
        self.clear_log_btn = QPushButton("Clear Logs")
        self.clear_log_btn.clicked.connect(lambda: self.log_console.clear())
        right_layout.addWidget(self.clear_log_btn)
        
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.splitter)
        self.statusBar().showMessage("Ready")

        self.file_manager.files_changed.connect(self.refresh_all_tabs)
        self.tabs.currentChanged.connect(self.tab_changed)

    @pyqtSlot(str)
    def append_log(self, text):
        cursor = self.log_console.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.log_console.setTextCursor(cursor)
        self.log_console.ensureCursorVisible()

    def refresh_all_tabs(self):
        num_funds = len(self.analyzer.funds)
        master = self.analyzer.get_master_holdings(asset_type_filter=None)
        total_unique = len(master) if not master.empty else 0
        
        cached_count = 0
        if total_unique > 0:
            for stock_name in master['Name']:
                from nse_symbol_map import resolve_nse_symbol
                sym = resolve_nse_symbol(stock_name)
                if sym and sym in price_fetcher._price_cache:
                    cached_count += 1
        
        curr_time = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.statusBar().showMessage(
            f"Funds: {num_funds} | Stocks tracked: {total_unique} | "
            f"Price data: {cached_count}/{total_unique} fetched | Last refresh: {curr_time}"
        )
        self.tab_changed(self.tabs.currentIndex())

    def tab_changed(self, index):
        widget = self.tabs.widget(index)
        if hasattr(widget, 'refresh_data'):
            widget.refresh_data()

    def export_data(self):
        if not self.analyzer.funds:
            QMessageBox.warning(self, "No Data", "Please upload at least one CSV file.")
            return
        export_dir = os.path.join(os.getcwd(), "exports")
        if not os.path.exists(export_dir): os.makedirs(export_dir)
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Export", os.path.join(export_dir, "MF_Analysis_Export.xlsx"), "Excel Files (*.xlsx)")
        if file_path:
            try:
                if export_to_excel(self.analyzer, file_path):
                    QMessageBox.information(self, "Success", f"Exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {e}")

def exception_hook(exctype, value, tb_data):
    err_msg = f"{exctype.__name__}: {value}\n"
    err_msg += "".join(traceback.format_exception(exctype, value, tb_data))
    print(err_msg)
    with open("crash_report.log", "a") as f:
        f.write("\n" + "="*50 + "\n" + err_msg)

sys.excepthook = exception_hook

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
