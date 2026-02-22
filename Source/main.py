import sys
import os
import subprocess
import psutil
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QVBoxLayout,
                             QHBoxLayout, QCheckBox, QPushButton, QLabel,
                             QGridLayout, QWidget, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, QTimer


def _get_gpu_vram_percent():
    """Return (gpu_util_percent, vram_used_percent) from nvidia-smi or (None, None)."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None, None
        line = out.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            return None, None
        gpu_pct = float(parts[0].replace("%", "").strip())
        mem_used = float(parts[1].strip().split()[0])
        mem_total = float(parts[2].strip().split()[0])
        vram_pct = (mem_used / mem_total * 100.0) if mem_total > 0 else 0.0
        return gpu_pct, vram_pct
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None, None


# Allow running from project root or from this file's directory
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir and _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

try:
    from stress_runner import start_stress, stop_stress
except ImportError:
    def start_stress(_config):
        return None, None
    def stop_stress(_process):
        pass

# Styling the window, kinda sort
DARK_STYLE = """
    QMainWindow, QDialog, QWidget {
        background-color: #1e1e1e;
        color: #dcdcdc;
        font-family: 'Segoe UI', Arial;
    }
    QLabel { color: #ffffff; }
    QCheckBox { spacing: 10px; font-size: 14px; }
    QCheckBox::indicator { width: 18px; height: 18px; }
    QPushButton {
        background-color: #3a3a3a;
        border: 1px solid #555555;
        padding: 10px 20px;
        color: white;
        font-weight: bold;
        border-radius: 5px;
    }
    QPushButton:hover { background-color: #505050; border: 1px solid #007acc; }
    QFrame#Tile {
        background-color: #252526;
        border: 1px solid #333333;
        border-radius: 8px;
    }
"""

class SelectionDialog(QDialog):

    def __init__(self):

        #Sets up basic style
        super().__init__()
        self.setWindowTitle("All-in-One-Benchmark - Selection")
        self.setFixedSize(350, 300)
        self.setStyleSheet(DARK_STYLE)
        
        #Makes the layout with proper margins
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 00, 20)
        
        #Just a header for fancyness
        header = QLabel("<h1>Hardware Selection</h1>")
        header.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(header)

        #Makes all the checkboxes with proper names
        self.check_cpu = QCheckBox("Stress Test CPU")
        self.check_gpu = QCheckBox("Stress Test GPU")
        self.check_ram = QCheckBox("Stress Test RAM")
        self.check_vram = QCheckBox("Stress Test VRAM")

        #Makes all of the checkboxes actually appear
        for cb in [self.check_cpu, self.check_gpu, self.check_ram, self.check_vram]:
            layout.addWidget(cb)
            
        layout.addSpacing(55)
        
        #Launch button
        self.start_btn = QPushButton("LAUNCH DASHBOARD")
        self.start_btn.clicked.connect(self.accept)
        layout.addWidget(self.start_btn)
        
        self.setLayout(layout)


    #This just gets which one of the checkboxes is actually checked
    def get_selected(self):

        #Returns the state of the checkboxes
        return {
            "cpu": self.check_cpu.isChecked(),
            "gpu": self.check_gpu.isChecked(),
            "ram": self.check_ram.isChecked(),
            "vram": self.check_vram.isChecked()
        }

class DashboardWindow(QMainWindow):

    #Basic setup
    def __init__(self, config):

        super().__init__()
        self.setWindowTitle("Apex Performance Dashboard")
        self.resize(1100, 750)
        self.setStyleSheet(DARK_STYLE)
        self.config = config

        #Data history for graphs (60 samples)
        self.history_limit = 60
        self.data_store = {
            "cpu": [0] * self.history_limit,
            "gpu": [0] * self.history_limit,
            "ram": [0] * self.history_limit,
            "vram": [0] * self.history_limit
        }

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # More header layout stuff
        info_label = QLabel("REAL-TIME SYSTEM TELEMETRY")
        info_label.setStyleSheet("letter-spacing: 2px; color: #007acc; font-weight: bold;")
        main_layout.addWidget(info_label)

        # 2x2 Grid for graphs and temps
        grid = QGridLayout()
        self.tiles = {}

        # Initialize graphs/monitors
        self.tiles['cpu'] = self.create_monitor_tile("CPU", "#00bfff")
        self.tiles['gpu'] = self.create_monitor_tile("GPU", "#ff4500")
        self.tiles['ram'] = self.create_monitor_tile("RAM", "#32cd32")
        self.tiles['vram'] = self.create_monitor_tile("VRAM", "#ff00ff")

        grid.addWidget(self.tiles['cpu']['frame'], 0, 0)
        grid.addWidget(self.tiles['gpu']['frame'], 0, 1)
        grid.addWidget(self.tiles['ram']['frame'], 1, 0)
        grid.addWidget(self.tiles['vram']['frame'], 1, 1)

        main_layout.addLayout(grid)

        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_stats)
        self.timer.start(1000)


    #Making each indivdual graph
    def create_monitor_tile(self, name, color):
        frame = QFrame()
        frame.setObjectName("Tile")
        layout = QVBoxLayout(frame)

        # Title and Live Readout
        head_layout = QHBoxLayout()
        title = QLabel(f"<h3>{name}</h3>")
        val_label = QLabel("0%")
        val_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        head_layout.addWidget(title)
        head_layout.addStretch()
        head_layout.addWidget(val_label)
        layout.addLayout(head_layout)

        # Graph
        graph = pg.PlotWidget()
        graph.setBackground('transparent')
        graph.setMouseEnabled(x=False, y=False)
        graph.setYRange(0, 100)
        graph.setXRange(0,60)
        
        pen = pg.mkPen(color=color, width=3)
        curve = graph.plot(self.data_store[name.lower()], pen=pen)
        layout.addWidget(graph)

        # Footer stats
        temp_label = QLabel("TEMP: --°C")
        temp_label.setStyleSheet("color: #888888;")
        layout.addWidget(temp_label)
        
        return {'frame': frame, 'label': val_label, 'temp': temp_label, 'curve': curve, 'key': name.lower()}

    def refresh_stats(self):
        # 1. Update CPU
        cpu_usage = psutil.cpu_percent()
        self.update_tile('cpu', cpu_usage)

        # 2. Update RAM
        ram_usage = psutil.virtual_memory().percent
        self.update_tile('ram', ram_usage)

        # 3. GPU / VRAM (real data via nvidia-smi when available)
        gpu_pct, vram_pct = _get_gpu_vram_percent()
        self.update_tile('gpu', (gpu_pct or 0) if self.config['gpu'] else 0)
        self.update_tile('vram', (vram_pct or 0) if self.config['vram'] else 0)

    def update_tile(self, key, value):
        # Update data list
        self.data_store[key].pop(0)
        self.data_store[key].append(value)
        
        # Update UI components
        self.tiles[key]['curve'].setData(self.data_store[key])
        self.tiles[key]['label'].setText(f"{int(value)}%")

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Run Stage 1
    selector = SelectionDialog()
    if getattr(selector, "exec")() == QDialog.DialogCode.Accepted:
        config = selector.get_selected()

        # Start C++ stress backend when at least one option is selected
        stress_process, stress_error = start_stress(config)
        if stress_error:
            QMessageBox.warning(
                None,
                "Stress backend not started",
                stress_error,
            )

        # Run Stage 2: dashboard
        dashboard = DashboardWindow(config)
        dashboard.show()

        def on_quit():
            stop_stress(stress_process)

        app.aboutToQuit.connect(on_quit)
        sys.exit(getattr(app, "exec")())