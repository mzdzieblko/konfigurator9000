# main_qt.py

import os
import sys
import json
import logging
import paramiko
import keyring
from qt_material import apply_stylesheet
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFileDialog,
    QMessageBox, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt
import time

# --- LOGOWANIE ---
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "app.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# --- STAŁE KOLUMN I PREFIXÓW ---
COLUMNS = [
    ("NASZE URZĄDZENIA", "192.168.255."),
    ("OPER-T",        "172.16.2."),
    ("OMEX",          "172.16.3."),
    ("POZOSTAŁE",     None),
]

# --- GŁÓWNE OKNO ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Menedżer logowania Comms")
        self.resize(800, 600)

        # Wczytaj dane
        self.accounts = self._load_json("accounts.json", [])
        self.devices  = self._load_json("devices.json", [])

        # Główny layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Pasek wyboru konta
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Konto SSH:"))
        self.acc_cb = QComboBox()
        self.acc_cb.addItems(self.accounts)
        row1.addWidget(self.acc_cb)
        main_layout.addLayout(row1)

        # Sekcja kolumn z urządzeniami w scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll_layout = QHBoxLayout(container)
        for title, prefix in COLUMNS:
            gb = QGroupBox(title)
            vbx = QVBoxLayout()
            # dodaj przyciski urządzeń
            for dev in self.devices:
                if prefix is None or dev["ip"].startswith(prefix):
                    btn = QPushButton(dev["name"])
                    btn.clicked.connect(lambda _, name=dev["name"]: self.on_device_button(name))
                    vbx.addWidget(btn)
            gb.setLayout(vbx)
            scroll_layout.addWidget(gb)
        container.setLayout(scroll_layout)
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # Label wybranego urządzenia
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Wybrane urządzenie:"))
        self.dev_label = QLabel("")
        row2.addWidget(self.dev_label)
        main_layout.addLayout(row2)

        # Przycisk wykonania skryptu
        self.run_btn = QPushButton("Wykonaj skrypt")
        self.run_btn.clicked.connect(self.execute_script)
        main_layout.addWidget(self.run_btn, alignment=Qt.AlignCenter)

    def _load_json(self, fname, default):
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            self._save_json(fname, default)
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            self._save_json(fname, default)
            return default

    def _save_json(self, fname, data):
        path = os.path.join(DATA_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def on_device_button(self, name):
        # Ustaw wybrane urządzenie
        self.selected_device = name
        self.dev_label.setText(name)
        logging.info(f"Device selected: {name}")

    def execute_script(self):
        acct = self.acc_cb.currentText()
        dev  = getattr(self, 'selected_device', None)
        if not acct or not dev:
            QMessageBox.warning(self, "Brak danych", "Wybierz konto i urządzenie.")
            return

        # wybór pliku
        path, _ = QFileDialog.getOpenFileName(
            self, "Wybierz plik z komendami", "", "Tekst (*.txt *.cmd);;Wszystkie pliki (*)"
        )
        if not path:
            return

        # pobierz dane logowania
        ip = next(d["ip"] for d in self.devices if d["name"] == dev)
        user = keyring.get_password("CommsLoginUser", acct)
        pwd  = keyring.get_password("CommsLoginPwd", acct)
        if user is None or pwd is None:
            QMessageBox.critical(self, "Brak poświadczeń", "Nie znaleziono loginu/hasła.")
            return

        # SSH Paramiko w trybie shell
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(ip, username=user, password=pwd)
        except Exception as e:
            logging.error(f"SSH connect failed: {e}")
            QMessageBox.critical(self, "Błąd SSH", str(e))
            return

        chan = client.invoke_shell()
        time.sleep(1)
        if chan.recv_ready():
            chan.recv(4096)

        # wykonaj komendy
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                cmd = line.strip()
                if not cmd:
                    continue
                logging.info(f">>> {cmd}")
                chan.send(cmd + "\n")
                time.sleep(0.5)
                output = ""
                while chan.recv_ready():
                    output += chan.recv(4096).decode("utf-8", "ignore")
                if output.strip():
                    logging.info(output.strip())

        chan.close()
        client.close()
        QMessageBox.information(self, "Sukces", "Wykonano komendy. Sprawdź logi.")

# --- START APLIKACJI ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="light_blue.xml")  # motyw Windows11-blue
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
