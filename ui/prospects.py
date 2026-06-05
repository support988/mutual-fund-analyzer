from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QSpinBox, QDoubleSpinBox, 
                             QLabel, QSplitter, QHeaderView, QMessageBox, QFileDialog,
                             QApplication, QComboBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import os
import pandas as pd
from exporter import export_prospects_report
import bulk_deals_parser
import price_fetcher

class ExtendedDataWorker(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, stock_name):
        super().__init__()
        self.stock_name = stock_name
    def run(self):
        data = price_fetcher.get_extended_data(self.stock_name)
        self.finished.emit(data)

class ProspectsAnalysisWorker(QThread):
    finished = pyqtSignal(int, list)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id, analyzer, asset_filter):
        super().__init__()
        self.request_id = request_id
        self.analyzer = analyzer
        self.asset_filter = asset_filter

    def run(self):
        try:
            prospects = self.analyzer.get_investment_prospects(asset_type_filter=self.asset_filter)
            self.finished.emit(self.request_id, prospects)
        except Exception as e:
            self.failed.emit(self.request_id, str(e))

class ProspectsWidget(QWidget):
    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer
        self.prospects_data = []
        self.bulk_df = None
        self.worker = None
        self.fundamental_workers = []
        self.analysis_worker = None
        self.analysis_request_id = 0
        self.cursor_is_overridden = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Row 1: Controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Min Funds Holding:"))
        self.min_funds_spin = QSpinBox()
        self.min_funds_spin.setRange(2, 20)
        self.min_funds_spin.setValue(2)
        ctrl_layout.addWidget(self.min_funds_spin)

        ctrl_layout.addWidget(QLabel("Min Composite Score:"))
        self.min_score_spin = QDoubleSpinBox()
        self.min_score_spin.setRange(0, 100)
        self.min_score_spin.setValue(10.0)
        ctrl_layout.addWidget(self.min_score_spin)

        ctrl_layout.addWidget(QLabel("Assets:"))
        self.asset_filter = QComboBox()
        self.asset_filter.addItems(["Equity Only", "All Asset Types"])
        self.asset_filter.currentIndexChanged.connect(self.refresh_data)
        ctrl_layout.addWidget(self.asset_filter)

        self.refresh_btn = QPushButton("Refresh Analysis")
        self.refresh_btn.clicked.connect(self.refresh_data)
        ctrl_layout.addWidget(self.refresh_btn)

        self.bulk_deals_btn = QPushButton("Upload Bulk Deals CSV (NSE/BSE)")
        self.bulk_deals_btn.clicked.connect(self.upload_bulk_deals)
        ctrl_layout.addWidget(self.bulk_deals_btn)
        
        self.bulk_status_label = QLabel("Bulk Deals: Not loaded")
        ctrl_layout.addWidget(self.bulk_status_label)

        self.export_btn = QPushButton("Export Prospect Report (.xlsx)")
        self.export_btn.clicked.connect(self.export_prospects)
        ctrl_layout.addWidget(self.export_btn)
        
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # Row 2: Rank Table
        self.rank_table = QTableWidget()
        self.rank_table.setColumnCount(16)
        self.rank_table.setHorizontalHeaderLabels([
            "Rank", "Stock", "Sector", "Funds Holding", "Breadth %", 
            "Avg Momentum (3M %)", "Conviction %", "New Entrants", 
            "YF Status", "Current Price", "Active Buy Signal",
            "Price vs 52W High", "Volume Spike", "Spike Date",
            "Price After Spike", "Composite Score"
        ])
        self.rank_table.setSortingEnabled(True)
        self.rank_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.rank_table.horizontalHeader().setStretchLastSection(True)
        self.rank_table.cellClicked.connect(self.on_cell_clicked)
        main_splitter.addWidget(self.rank_table)

        # Row 3: Detail Panel
        detail_panel = QWidget()
        detail_layout = QHBoxLayout(detail_panel)
        detail_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT SIDE: Charts
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(6, 8), constrained_layout=True)
        self.canvas = FigureCanvas(self.fig)
        left_layout.addWidget(self.canvas)
        detail_splitter.addWidget(left_widget)

        # RIGHT SIDE: Tables & Data
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        right_layout.addWidget(QLabel("Monthly Allocation % (Actual Figures)"))
        self.monthly_table = QTableWidget()
        self.monthly_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_layout.addWidget(self.monthly_table)
        
        right_layout.addWidget(QLabel("Change Analysis"))
        self.change_table = QTableWidget()
        self.change_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_layout.addWidget(self.change_table)
        
        # Fundamentals Section
        right_layout.addWidget(QLabel("<b>Fundamentals (Extended)</b>"))
        self.fundamentals_label = QLabel("Select a stock to see fundamentals")
        self.fundamentals_label.setWordWrap(True)
        self.fundamentals_label.setStyleSheet("padding: 5px; background-color: #f9f9f9; border: 1px solid #ddd;")
        right_layout.addWidget(self.fundamentals_label)

        right_layout.addWidget(QLabel("Bulk Deals Confirmation"))
        self.bulk_deals_table = QTableWidget()
        self.bulk_deals_table.setColumnCount(6)
        self.bulk_deals_table.setHorizontalHeaderLabels(["Date", "Client Name", "Type", "Qty", "Price", "Value"])
        right_layout.addWidget(self.bulk_deals_table)
        
        self.bulk_verdict_label = QLabel("Upload NSE/BSE Bulk Deals CSV to see deal confirmation")
        self.bulk_verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border: 1px solid #ccc;")
        right_layout.addWidget(self.bulk_verdict_label)

        detail_splitter.addWidget(right_widget)
        detail_layout.addWidget(detail_splitter)
        
        main_splitter.addWidget(detail_panel)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        layout.addWidget(main_splitter)

        # Footer
        self.footer_label = QLabel("Score Breakdown: -")
        layout.addWidget(self.footer_label)

        self.setLayout(layout)
        
        self.setStyleSheet("""
            ProspectsWidget { background-color: white; }
            QWidget { color: black; }
            QHeaderView::section { color: black; background-color: #f0f0f0; }
            QTableWidget { gridline-color: #d0d0d0; background-color: white; }
            QLabel { color: black; }
            QPushButton { color: black; background-color: #e1e1e1; border: 1px solid #aaa; padding: 5px; }
            QSpinBox, QDoubleSpinBox, QComboBox { color: black; background-color: white; }
            QComboBox QAbstractItemView {
                color: black;
                background-color: white;
                selection-color: white;
                selection-background-color: #2563eb;
            }
        """)

    def upload_bulk_deals(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Bulk Deals CSV", "", "CSV Files (*.csv)")
        if file_path:
            df = bulk_deals_parser.parse_bulk_deals_csv(file_path)
            if not df.empty:
                self.bulk_df = df
                min_date = df['date'].min().strftime('%d-%b-%Y')
                max_date = df['date'].max().strftime('%d-%b-%Y')
                self.bulk_status_label.setText(f"Bulk Deals: {len(df)} records ({min_date} to {max_date})")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "Failed to parse bulk deals CSV.")

    def refresh_data(self):
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.footer_label.setText("Score Breakdown: Analysis already running...")
            return

        self.analysis_request_id += 1
        request_id = self.analysis_request_id
        asset_filter_val = "Equity" if self.asset_filter.currentText() == "Equity Only" else None

        self.set_controls_enabled(False)
        self.rank_table.setSortingEnabled(False)
        self.rank_table.setRowCount(0)
        self.footer_label.setText("Score Breakdown: Loading prospects...")
        self.set_wait_cursor()

        self.analysis_worker = ProspectsAnalysisWorker(request_id, self.analyzer, asset_filter_val)
        self.analysis_worker.finished.connect(self.on_analysis_finished)
        self.analysis_worker.failed.connect(self.on_analysis_failed)
        self.analysis_worker.start()

    @pyqtSlot(int, list)
    def on_analysis_finished(self, request_id, prospects):
        if request_id != self.analysis_request_id:
            return
        self.prospects_data = prospects
        self.populate_rank_table()
        self.set_controls_enabled(True)
        self.restore_wait_cursor()

    @pyqtSlot(int, str)
    def on_analysis_failed(self, request_id, error):
        if request_id != self.analysis_request_id:
            return
        self.set_controls_enabled(True)
        self.restore_wait_cursor()
        QMessageBox.critical(self, "Error", f"Failed to refresh prospects: {error}")

    def set_controls_enabled(self, enabled):
        self.refresh_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)
        self.bulk_deals_btn.setEnabled(enabled)
        self.asset_filter.setEnabled(enabled)
        self.min_funds_spin.setEnabled(enabled)
        self.min_score_spin.setEnabled(enabled)

    def set_wait_cursor(self):
        if not self.cursor_is_overridden:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.cursor_is_overridden = True

    def restore_wait_cursor(self):
        if self.cursor_is_overridden:
            QApplication.restoreOverrideCursor()
            self.cursor_is_overridden = False

    def populate_rank_table(self):
        min_funds = self.min_funds_spin.value()
        min_score = self.min_score_spin.value()

        filtered = [
            p for p in self.prospects_data
            if p['funds_holding'] >= min_funds and p['composite_score'] >= min_score
        ]

        self.rank_table.setSortingEnabled(False)
        self.rank_table.setRowCount(len(filtered))
        for i, p in enumerate(filtered):
            items = [
                QTableWidgetItem(str(i+1)),
                QTableWidgetItem(p['stock']),
                QTableWidgetItem(p['sector']),
                QTableWidgetItem(str(p['funds_holding'])),
                QTableWidgetItem(f"{p['breadth_score']:.1f}%"),
                QTableWidgetItem(f"{p['momentum_score']:.2f}%"),
                QTableWidgetItem(f"{p['conviction_score']:.1f}%"),
                QTableWidgetItem(str(p['new_entrants']))
            ]

            yf_status = "Connected" if p['price_data_available'] else "No Data"
            yf_item = QTableWidgetItem(yf_status)
            if p['price_data_available']:
                yf_item.setBackground(QColor("#d4edda"))
                yf_item.setForeground(QColor("#155724"))
            else:
                yf_item.setBackground(QColor("#e2e3e5"))
                yf_item.setForeground(QColor("#383d41"))
            items.append(yf_item)

            current_price = f"{p['price_data']['current_price']:.2f}" if p['price_data'] else "N/A"
            items.append(QTableWidgetItem(current_price))

            abs_signal = p['active_buy_signal']['signal'] if p['active_buy_signal'] else "N/A"
            items.append(QTableWidgetItem(abs_signal))

            p52w = f"{p['price_data']['pct_below_52w_high']:.1f}%" if p['price_data'] else "N/A"
            items.append(QTableWidgetItem(p52w))

            if p['price_data']:
                spike = "Yes" if p['price_data'].get('volume_spike') else "No"
                spike_date = p['price_data'].get('latest_volume_spike_date') or "N/A"
                if p['price_data'].get('price_change_since_volume_spike') is not None:
                    post_spike = f"{p['price_data']['price_change_since_volume_spike']:+.1f}%"
                else:
                    post_spike = "N/A"
            else:
                spike = "N/A"
                spike_date = "N/A"
                post_spike = "N/A"
            items.append(QTableWidgetItem(spike))
            items.append(QTableWidgetItem(spike_date))
            items.append(QTableWidgetItem(post_spike))

            items.append(QTableWidgetItem(f"{p['composite_score']:.1f}"))

            bg_color = QColor("#f8d7da")
            text_color = QColor(0, 0, 0)
            if p['composite_score'] >= 60:
                bg_color = QColor(40, 167, 69)
                text_color = QColor(255, 255, 255)
            elif p['composite_score'] >= 35:
                bg_color = QColor(255, 193, 7)
                text_color = QColor(0, 0, 0)

            for idx, item in enumerate(items):
                if idx != 8:
                    item.setBackground(bg_color)
                    item.setForeground(text_color)

            for j, item in enumerate(items):
                self.rank_table.setItem(i, j, item)

        self.rank_table.setSortingEnabled(True)
        if self.rank_table.rowCount() > 0:
            self.rank_table.selectRow(0)
            self.on_cell_clicked(0, 0)
        else:
            self.footer_label.setText("Score Breakdown: No prospects matched the current filters.")

    def on_cell_clicked(self, row, col):
        stock_name = self.rank_table.item(row, 1).text()
        prospect = next((p for p in self.prospects_data if p['stock'] == stock_name), None)
        if prospect:
            self.load_stock_detail(prospect)

    def on_rank_selection(self):
        rows = self.rank_table.selectionModel().selectedRows()
        if not rows:
            return
        self.on_cell_clicked(rows[0].row(), 0)

    def load_stock_detail(self, p):
        # Update Footer
        accel_pts = min(p['breadth_acceleration']*5, 15)
        reduction_txt = f" | Cons. Red: {p['consecutive_reduction']}" if p['consecutive_reduction'] > 0 else ""
        self.footer_label.setText(
            f"Score Breakdown: Breadth {p['breadth_score']:.1f}/100 x 25% + "
            f"Momentum {p['momentum_score']:.2f}% x 10 x 30% + "
            f"Conviction {p['conviction_score']:.1f}/100 x 20% + "
            f"Accel {accel_pts} pts + "
            f"Active Buy Bonus {p['active_buy_signal']['score_bonus'] if p['active_buy_signal'] else 0} = {p['composite_score']:.1f}"
            f"{reduction_txt} | Sector Momentum: {p['sector_momentum_count']}"
        )
        
        if p['price_data_available']:
            pd_info = p['price_data']
            price_text = f"\nPrice Context: Current Rs {pd_info['current_price']:.2f} | 52W High Rs {pd_info['price_52w_high']:.2f} | " \
                         f"{pd_info['pct_below_52w_high']:.1f}% below 52W High | 3M Price Change: {pd_info['price_change_3m']:+.1f}%"
            if pd_info.get('volume_spike'):
                price_text += (
                    f"\nVolume Spike: {pd_info['volume_spike_ratio']:.1f}x on "
                    f"{pd_info['latest_volume_spike_date']} | Price since spike: "
                    f"{pd_info['price_change_since_volume_spike']:+.1f}% "
                    f"over {pd_info['days_since_volume_spike']} days"
                )
            else:
                price_text += "\nVolume Spike: None in the last 3 trading months"
            
            abs_text = ""
            if p['active_buy_signal']:
                sig = p['active_buy_signal']['signal']
                expl = p['active_buy_signal']['explanation']
                if sig == 'strong_buy': abs_text = f"Strong Active Buy - {expl}"
                elif sig == 'active_buy': abs_text = f"Active Buy Confirmed - {expl}"
                elif sig == 'passive_drift': abs_text = f"Passive Drift - {expl}"
                elif sig == 'partial_sell': abs_text = f"Partial Sell Detected - {expl}"
                elif sig == 'reducing': abs_text = f"Reducing - {expl}"
            
            self.footer_label.setText(self.footer_label.text() + price_text + "\n" + abs_text)
            
            # Use threading for Fundamentals to avoid UI freeze
            self.fundamentals_label.setText("Fetching fundamentals...")
            if self.worker and self.worker.isRunning():
                try:
                    self.worker.finished.disconnect()
                except TypeError:
                    pass
                old_worker = self.worker
                old_worker.finished.connect(lambda _data, worker=old_worker: self.cleanup_fundamentals_worker(worker))

            worker = ExtendedDataWorker(p['stock'])
            self.worker = worker
            self.fundamental_workers.append(worker)
            worker.finished.connect(self.on_fundamentals_fetched)
            worker.finished.connect(lambda _data, worker=worker: self.cleanup_fundamentals_worker(worker))
            worker.start()
        else:
            self.footer_label.setText(self.footer_label.text() + "\nPrice data unavailable for this stock (symbol not mapped)")
            self.fundamentals_label.setText("Select a stock with mapped symbol for fundamentals.")

        # Update Bulk Deals if loaded
        if self.bulk_df is not None:
            activity = bulk_deals_parser.get_mf_bulk_activity(self.bulk_df, p['stock'])
            self.bulk_verdict_label.setText(f"Verdict: {activity['verdict']}")
            
            v = activity['verdict']
            if v == 'Strong MF Buying': self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;")
            elif v == 'Mixed': self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba;")
            elif v == 'MF Selling': self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;")
            else: self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #e2e3e5; color: #383d41; border: 1px solid #d6d8db;")
            
            self.bulk_deals_table.setRowCount(len(activity['deals']))
            for i, d in enumerate(activity['deals']):
                self.bulk_deals_table.setItem(i, 0, QTableWidgetItem(str(d['date'])))
                self.bulk_deals_table.setItem(i, 1, QTableWidgetItem(str(d['client_name'])))
                self.bulk_deals_table.setItem(i, 2, QTableWidgetItem(str(d['deal_type'])))
                self.bulk_deals_table.setItem(i, 3, QTableWidgetItem(f"{d['quantity']:,}"))
                self.bulk_deals_table.setItem(i, 4, QTableWidgetItem(f"{d['price']:.2f}"))
                self.bulk_deals_table.setItem(i, 5, QTableWidgetItem(f"{d['quantity']*d['price']:,.0f}"))
        else:
            self.bulk_verdict_label.setText("Upload NSE/BSE Bulk Deals CSV to see deal confirmation")
            self.bulk_verdict_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border: 1px solid #ccc;")
            self.bulk_deals_table.setRowCount(0)

        # Update Charts
        self.ax1.clear()
        self.ax2.clear()
        
        all_dates_set = set()
        for fd in p['fund_details']:
            all_dates_set.update(fd['monthly_series'].keys())
        all_dates = sorted(list(all_dates_set))
        
        for fd in p['fund_details']:
            dates_sorted = sorted(fd['monthly_series'].keys())
            vals = [fd['monthly_series'][d] for d in dates_sorted]
            date_objs = [pd.to_datetime(d) for d in dates_sorted]
            self.ax1.plot(date_objs, vals, label=fd['fund'], alpha=0.5, linewidth=1.2)
            
        ts = self.analyzer.get_stock_time_series(p['stock'])
        self.ax1.plot(ts['Date'], ts['AVERAGE'], label='AVERAGE', linewidth=2.5, color='black', marker='o', markersize=4)
        self.ax1.set_title(p['stock'])
        self.ax1.set_ylabel("Allocation %")
        self.ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize='small')
        self.ax1.grid(True)

        short_funds = [fd['fund'] for fd in p['fund_details']]
        latest_allocs = [fd['latest_alloc'] for fd in p['fund_details']]
        colors = []
        for fd in p['fund_details']:
            if fd['change_3m'] > 0: colors.append('green')
            elif fd['change_3m'] < 0: colors.append('red')
            else: colors.append('grey')
            
        bars = self.ax2.bar(short_funds, latest_allocs, color=colors)
        self.ax2.set_ylabel("Allocation %")
        latest_month_label = pd.to_datetime(all_dates[-1]).strftime('%b-%y') if all_dates else ""
        self.ax2.set_title(f"Latest Snapshot - {latest_month_label}")
        plt.setp(self.ax2.get_xticklabels(), rotation=30, horizontalalignment='right')
        for bar in bars:
            h = bar.get_height()
            self.ax2.text(bar.get_x() + bar.get_width()/2., h, f'{h:.1f}%', ha='center', va='bottom', fontsize=8)
            
        self.canvas.draw()

        # Update Monthly Table
        self.monthly_table.clear()
        self.monthly_table.setRowCount(len(p['fund_details']) + 1)
        col_headers = ["Fund"] + [pd.to_datetime(d).strftime('%b-%y') for d in all_dates]
        self.monthly_table.setColumnCount(len(col_headers))
        self.monthly_table.setHorizontalHeaderLabels(col_headers)
        
        avg_row_vals = []
        for d_str in all_dates:
            vals = [fd['monthly_series'].get(d_str, 0) for fd in p['fund_details'] if fd['monthly_series'].get(d_str, 0) > 0]
            avg_row_vals.append(sum(vals)/len(vals) if vals else 0)

        for i, fd in enumerate(p['fund_details']):
            self.monthly_table.setItem(i, 0, QTableWidgetItem(fd['fund']))
            for j, d_str in enumerate(all_dates):
                val = fd['monthly_series'].get(d_str, 0)
                item = QTableWidgetItem(f"{val:.2f}" if val > 0 else "0.00")
                
                text_color = QColor(0,0,0)
                if j > 0:
                    prev_val = fd['monthly_series'].get(all_dates[j-1], 0)
                    if val > prev_val: 
                        item.setBackground(QColor(40, 167, 69))
                        text_color = QColor(255, 255, 255)
                    elif val < prev_val: 
                        item.setBackground(QColor(220, 53, 69))
                        text_color = QColor(255, 255, 255)
                
                item.setForeground(text_color)
                self.monthly_table.setItem(i, j+1, item)
                
        idx_avg = len(p['fund_details'])
        avg_item = QTableWidgetItem("AVERAGE")
        avg_item.setFont(self.rank_table.font()) 
        self.monthly_table.setItem(idx_avg, 0, avg_item)
        for j, val in enumerate(avg_row_vals):
            item = QTableWidgetItem(f"{val:.2f}")
            item.setForeground(QColor(0,0,0))
            self.monthly_table.setItem(idx_avg, j+1, item)

        # Update Change Analysis Table
        self.change_table.setRowCount(len(p['fund_details']) + 1)
        self.change_table.setColumnCount(5)
        self.change_table.setHorizontalHeaderLabels(["Fund", "Latest %", "1M Change", "3M Change", "Trend"])
        
        sum_1m = 0
        sum_3m = 0
        sum_latest = 0
        
        for i, fd in enumerate(p['fund_details']):
            self.change_table.setItem(i, 0, QTableWidgetItem(fd['fund']))
            self.change_table.setItem(i, 1, QTableWidgetItem(f"{fd['latest_alloc']:.2f}"))
            
            c1 = fd['change_1m']
            item_1m = QTableWidgetItem(f"{c1:+.2f}")
            item_1m.setForeground(QColor("green" if c1 > 0 else ("red" if c1 < 0 else "black")))
            self.change_table.setItem(i, 2, item_1m)
            
            c3 = fd['change_3m']
            item_3m = QTableWidgetItem(f"{c3:+.2f}")
            item_3m.setForeground(QColor("green" if c3 > 0 else ("red" if c3 < 0 else "black")))
            self.change_table.setItem(i, 3, item_3m)
            
            trend = "Stable"
            if c3 > 0.5: trend = "Building"
            elif c3 < -0.5: trend = "Reducing"
            self.change_table.setItem(i, 4, QTableWidgetItem(trend))
            
            sum_1m += c1
            sum_3m += c3
            sum_latest += fd['latest_alloc']

        avg_idx = len(p['fund_details'])
        self.change_table.setItem(avg_idx, 0, QTableWidgetItem("AVERAGE"))
        self.change_table.setItem(avg_idx, 1, QTableWidgetItem(f"{sum_latest/len(p['fund_details']):.2f}"))
        self.change_table.setItem(avg_idx, 2, QTableWidgetItem(f"{sum_1m/len(p['fund_details']):+.2f}"))
        self.change_table.setItem(avg_idx, 3, QTableWidgetItem(f"{sum_3m/len(p['fund_details']):+.2f}"))
        
        self.rank_table.resizeColumnsToContents()
        self.monthly_table.resizeColumnsToContents()
        self.change_table.resizeColumnsToContents()
        self.bulk_deals_table.resizeColumnsToContents()

    @pyqtSlot(dict)
    def on_fundamentals_fetched(self, ext):
        if ext:
            def fmt_number(value, suffix="", decimals=1):
                return f"{value:,.{decimals}f}{suffix}" if value is not None else "N/A"

            market_cap = fmt_number(ext.get('market_cap_cr'), " Cr", 0)
            pe_ratio = ext.get('pe_ratio') if ext.get('pe_ratio') is not None else 'N/A'
            pb_ratio = ext.get('pb_ratio') if ext.get('pb_ratio') is not None else 'N/A'
            promoter = fmt_number(ext.get('promoter_holding_pct'), "%")
            fii = fmt_number(ext.get('fii_holding_pct'), "%")
            earnings = ext.get('earnings_date') or 'N/A'

            f_txt = f"<b>Mkt Cap:</b> Rs {market_cap} | <b>PE:</b> {pe_ratio} | <b>PB:</b> {pb_ratio}<br>" \
                    f"<b>Promoter:</b> {promoter} | <b>FII:</b> {fii}<br>" \
                    f"<b>Next Earnings:</b> {earnings}"
            if ext.get('upcoming_earnings_flag'):
                f_txt += " <font color='red'>(UPCOMING)</font>"
            self.fundamentals_label.setText(f_txt)
        else:
            self.fundamentals_label.setText("Extended data unavailable.")

    def cleanup_fundamentals_worker(self, worker):
        if worker in self.fundamental_workers:
            self.fundamental_workers.remove(worker)

    def export_prospects(self):
        export_dir = os.path.join(os.getcwd(), "exports")
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Prospect Report", os.path.join(export_dir, "Investment_Prospects_Report.xlsx"), "Excel Files (*.xlsx)")
        if file_path:
            try:
                asset_filter_val = "Equity" if self.asset_filter.currentText() == "Equity Only" else None
                success = export_prospects_report(self.analyzer, file_path, bulk_df=self.bulk_df, asset_type_filter=asset_filter_val)
                if success:
                    QMessageBox.information(self, "Success", f"Exported successfully to {file_path}")
                else:
                    QMessageBox.warning(self, "Failure", "Failed to generate report.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
