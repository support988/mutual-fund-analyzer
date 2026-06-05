import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel

def test():
    print("Testing PyQt6 initialization...")
    try:
        app = QApplication(sys.argv)
        print("QApplication created.")
        win = QMainWindow()
        win.setWindowTitle("Test Window")
        win.setCentralWidget(QLabel("PyQt6 is working!"))
        win.show()
        print("Window shown. If you can see this, it didn't crash yet.")
        # We don't call app.exec() because it's a non-interactive environment
        print("PyQt6 test passed.")
    except Exception as e:
        print(f"PyQt6 test failed: {e}")

if __name__ == "__main__":
    test()
