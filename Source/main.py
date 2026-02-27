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
    """Return (gpu_util_pct, vram_used_pct) from nvidia-smi or (None, None). Usage only; temps from LHM."""
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


def _get_gpu_vendor():
    """
    Detect primary GPU vendor. Returns (vendor, name) where vendor is
    'nvidia', 'amd', 'intel', or None; name is a short description (e.g. "NVIDIA GeForce RTX 3080").
    Used to show which driver/API will be used (CUDA for NVIDIA, OpenCL for AMD/Intel).
    """
    # 1. NVIDIA: nvidia-smi is authoritative
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if out.returncode == 0 and out.stdout.strip():
            name = out.stdout.strip().split("\n")[0].strip()
            return "nvidia", name or "NVIDIA GPU"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. Windows: WMI Win32_VideoController for AMD/Intel (or when nvidia-smi missing)
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                [
                    "wmic",
                    "path",
                    "win32_videocontroller",
                    "get",
                    "name,adaptercompatibility",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if out.returncode != 0 or not out.stdout.strip():
                return None, None
            lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
            if len(lines) < 2:
                return None, None
            # First line is header "Node,AdapterCompatibility,Name"
            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                name = (parts[-1] if len(parts) >= 3 else "").strip()
                compat = (parts[-2] if len(parts) >= 2 else "").strip().lower()
                if not name or "microsoft" in name.lower() or "basic" in name.lower():
                    continue
                if "nvidia" in name.lower() or "nvidia" in compat:
                    return "nvidia", name or "NVIDIA GPU"
                if "amd" in name.lower() or "amd" in compat or "radeon" in name.lower() or "ati " in name.lower():
                    return "amd", name or "AMD GPU"
                if "intel" in name.lower() or "intel" in compat:
                    return "intel", name or "Intel GPU"
            if lines[1:]:
                name = lines[1].split(",")[-1].strip() if "," in lines[1] else lines[1]
                return "unknown", name or "GPU"
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass

    return None, None


# Global handle for LibreHardwareMonitor; kept open for continuous reads (never closed in refresh).
_LHM_COMPUTER = None


def _get_lhm_readings():
    """
    Get CPU temp, GPU temp, GPU load, and VRAM load from LibreHardwareMonitorLib.dll (bundled with exe).
    Keeps the Computer instance open (_LHM_COMPUTER) for the next refresh; does not call Close().
    Windows only; returns {} if DLL missing or on error.
    """
    global _LHM_COMPUTER
    if sys.platform != "win32":
        return {}

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    dll_path = os.path.join(base, "LibreHardwareMonitorLib.dll")
    if not os.path.isfile(dll_path):
        return {}

    try:
        import clr
        clr.AddReference(os.path.abspath(dll_path))
        from LibreHardwareMonitor.Hardware import Computer, SensorType
    except Exception:
        return {}

    if _LHM_COMPUTER is None:
        _LHM_COMPUTER = Computer()
        _LHM_COMPUTER.IsCpuEnabled = True
        _LHM_COMPUTER.IsGpuEnabled = True
        _LHM_COMPUTER.IsMotherboardEnabled = True
        _LHM_COMPUTER.Open()

    out = {"cpu_temp": None, "gpu_temp": None, "gpu_load": None, "vram_load": None}
    cpu_temps = []
    seen_gpu_load = False
    seen_vram_load = False

    def is_gpu_hardware(name):
        n = name.lower()
        if "cpu" in n or "processor" in n:
            return False
        return any(x in n for x in ("gpu", "nvidia", "radeon", "amd", "graphics")) or ("intel" in n and "graphics" in n)

    def collect_sensors(hardware, hw_name):
        for sensor in getattr(hardware, "Sensors", []) or []:
            if getattr(sensor, "Value", None) is None:
                continue
            try:
                val = float(sensor.Value)
            except (TypeError, ValueError):
                continue
            is_temp = getattr(sensor, "SensorType", None) == SensorType.Temperature
            is_load = getattr(sensor, "SensorType", None) == SensorType.Load
            s_name = (getattr(sensor, "Name", None) or "").lower()

            if is_temp:
                if "cpu" in hw_name or "core" in s_name or "package" in s_name:
                    cpu_temps.append(val)
                elif is_gpu_hardware(hw_name):
                    if out["gpu_temp"] is None or val > (out["gpu_temp"] or 0):
                        out["gpu_temp"] = round(val, 1)
            elif is_load:
                if is_gpu_hardware(hw_name):
                    if "memory" in s_name or "vram" in s_name or "gpu memory" in s_name:
                        out["vram_load"] = round(val, 1)
                        seen_vram_load = True
                    else:
                        out["gpu_load"] = round(val, 1)
                        seen_gpu_load = True

    try:
        for hardware in _LHM_COMPUTER.Hardware:
            hardware.Update()
            hw_name = (getattr(hardware, "Name", None) or "").lower()
            collect_sensors(hardware, hw_name)
            for sub in getattr(hardware, "SubHardware", []) or []:
                sub.Update()
                collect_sensors(sub, hw_name)
        if cpu_temps:
            out["cpu_temp"] = round(max(cpu_temps), 1)
        if out["gpu_temp"] is not None:
            out["gpu_temp"] = round(out["gpu_temp"], 1)
        # Fallback for NVIDIA if LHM exposes temps but not load: use nvidia-smi percentages.
        if (not seen_gpu_load or not seen_vram_load) and out["gpu_temp"] is not None:
            gpu_pct, vram_pct = _get_gpu_vram_percent()
            if not seen_gpu_load and gpu_pct is not None:
                out["gpu_load"] = round(gpu_pct, 1)
            if not seen_vram_load and vram_pct is not None:
                out["vram_load"] = round(vram_pct, 1)
    except Exception:
        pass
    return out


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

        # Show detected GPU and which API will be used (CUDA for NVIDIA, OpenCL for AMD/Intel)
        vendor, gpu_name = _get_gpu_vendor()
        if vendor == "nvidia":
            gpu_hint = f"GPU: {gpu_name} (CUDA)"
        elif vendor == "amd":
            gpu_hint = f"GPU: {gpu_name} (OpenCL)"
        elif vendor == "intel":
            gpu_hint = f"GPU: {gpu_name} (OpenCL)"
        elif vendor == "unknown":
            gpu_hint = f"GPU: {gpu_name} (OpenCL if available)"
        else:
            gpu_hint = "GPU: Not detected"
        self.gpu_label = QLabel(gpu_hint)
        self.gpu_label.setStyleSheet("color: #888; font-size: 12px;")
        self.gpu_label.setWordWrap(True)
        layout.addWidget(self.gpu_label)

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

        # Data history (60 samples)
        self.history_limit = 60
        self.data_store = {
            "cpu": [0] * self.history_limit,
            "gpu": [0] * self.history_limit,
            "ram": [0] * self.history_limit,
            "vram": [0] * self.history_limit,
        }
        self.temp_store = {"cpu": [0] * self.history_limit, "gpu": [0] * self.history_limit}

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        info_label = QLabel("REAL-TIME SYSTEM TELEMETRY")
        info_label.setStyleSheet("letter-spacing: 2px; color: #007acc; font-weight: bold;")
        main_layout.addWidget(info_label)

        grid = QGridLayout()
        self.tiles = {}

        # Row 0: four usage graphs (CPU, RAM, GPU, VRAM)
        self.tiles["cpu"] = self._create_usage_tile("CPU", "#00bfff")
        self.tiles["ram"] = self._create_usage_tile("RAM", "#32cd32")
        self.tiles["gpu"] = self._create_usage_tile("GPU", "#ff4500")
        self.tiles["vram"] = self._create_usage_tile("VRAM", "#ff00ff")
        grid.addWidget(self.tiles["cpu"]["frame"], 0, 0)
        grid.addWidget(self.tiles["ram"]["frame"], 0, 1)
        grid.addWidget(self.tiles["gpu"]["frame"], 0, 2)
        grid.addWidget(self.tiles["vram"]["frame"], 0, 3)

        # Row 1: two temperature graphs (wider)
        # Pass explicit keys so CPU/GPU temps cannot be swapped by title text, GPU and CPU are switched here because LHM is dumb
        self.tiles["cpu_temp"] = self._create_temp_tile("GPU Temperature", "#ff4500", key="gpu")
        self.tiles["gpu_temp"] = self._create_temp_tile("CPU Temperature", "#00bfff", key="cpu")
        grid.addWidget(self.tiles["cpu_temp"]["frame"], 1, 0, 1, 2)
        grid.addWidget(self.tiles["gpu_temp"]["frame"], 1, 2, 1, 2)

        main_layout.addLayout(grid)

        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_stats)
        self.timer.start(1000)


    def _create_usage_tile(self, name, color):
        """Single usage graph (0–100%), no temperature."""
        frame = QFrame()
        frame.setObjectName("Tile")
        layout = QVBoxLayout(frame)
        key = name.lower()
        head_layout = QHBoxLayout()
        title = QLabel(f"<h3>{name}</h3>")
        val_label = QLabel("0%")
        val_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        head_layout.addWidget(title)
        head_layout.addStretch()
        head_layout.addWidget(val_label)
        layout.addLayout(head_layout)
        graph = pg.PlotWidget()
        graph.setBackground("transparent")
        graph.setMouseEnabled(x=False, y=False)
        graph.setXRange(0, self.history_limit)
        plot_item = graph.getPlotItem()
        plot_item.setYRange(0, 100)
        pen = pg.mkPen(color=color, width=3)
        curve = plot_item.plot(self.data_store[key], pen=pen)
        layout.addWidget(graph)
        return {"frame": frame, "label": val_label, "curve": curve, "key": key}

    def _create_temp_tile(self, title_text, color, key):
        """Single temperature-over-time graph with current value label. key is 'cpu' or 'gpu'."""
        frame = QFrame()
        frame.setObjectName("Tile")
        layout = QVBoxLayout(frame)
        head_layout = QHBoxLayout()
        title = QLabel(f"<h3>{title_text}</h3>")
        val_label = QLabel("--°C")
        val_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        head_layout.addWidget(title)
        head_layout.addStretch()
        head_layout.addWidget(val_label)
        layout.addLayout(head_layout)
        graph = pg.PlotWidget()
        graph.setBackground("transparent")
        graph.setMouseEnabled(x=False, y=False)
        graph.setXRange(0, self.history_limit)
        plot_item = graph.getPlotItem()
        plot_item.setYRange(0, 120)
        plot_item.setLabel("left", "°C")
        pen = pg.mkPen(color=color, width=3)
        curve = plot_item.plot(self.temp_store[key], pen=pen)
        layout.addWidget(graph)
        return {"frame": frame, "label": val_label, "curve": curve, "key": key}

    def refresh_stats(self):
        # All temperatures and GPU/VRAM load from LibreHardwareMonitorLib.dll only (bundled with exe).
        # CPU/RAM usage from psutil. GPU/VRAM usage from LHM when available, else nvidia-smi (NVIDIA only).

        lhm = _get_lhm_readings()

        # 1. CPU usage (psutil) and temperature (LHM only)
        cpu_usage = psutil.cpu_percent()
        self.update_usage("cpu", cpu_usage)
        self.update_temp("cpu", lhm.get("cpu_temp"))

        # 2. RAM usage
        ram_usage = psutil.virtual_memory().percent
        self.update_usage("ram", ram_usage)

        # 3. GPU / VRAM — usage from LHM (all vendors), fallback nvidia-smi for usage only; temp from LHM only
        gpu_load = lhm.get("gpu_load")
        vram_load = lhm.get("vram_load")
        if gpu_load is None or vram_load is None:
            gpu_pct, vram_pct = _get_gpu_vram_percent()
            if gpu_load is None:
                gpu_load = gpu_pct
            if vram_load is None:
                vram_load = vram_pct
        self.update_usage("gpu", gpu_load if gpu_load is not None else 0)
        self.update_usage("vram", vram_load if vram_load is not None else 0)
        self.update_temp("gpu", lhm.get("gpu_temp"))

    def update_usage(self, key, value):
        self.data_store[key].pop(0)
        self.data_store[key].append(value if value is not None else 0)
        self.tiles[key]["curve"].setData(self.data_store[key])
        self.tiles[key]["label"].setText(f"{int(value) if value is not None else 0}%")

    def update_temp(self, key, temp_value):
        """Update temperature history and the corresponding temp graph (cpu_temp or gpu_temp)."""
        if key not in self.temp_store:
            return
        self.temp_store[key].pop(0)
        self.temp_store[key].append(temp_value if temp_value is not None else 0)
        tile_key = f"{key}_temp"
        if tile_key in self.tiles:
            self.tiles[tile_key]["curve"].setData(self.temp_store[key])
            self.tiles[tile_key]["label"].setText(f"{temp_value}°C" if temp_value is not None else "--°C")

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

        # If stress backend exits immediately (e.g. missing VC++ Redist on a fresh PC), tell the user
        def check_stress_backend():
            if stress_process is not None and stress_process.poll() is not None:
                QMessageBox.warning(
                    None,
                    "Stress backend stopped",
                    "The stress process exited unexpectedly. On a new PC, install:\n"
                    "Microsoft Visual C++ Redistributable for Visual Studio 2015-2022 (x64)\n"
                    "(Download from Microsoft or use: winget install Microsoft.VCRedist.2015+.x64)",
                )
        QTimer.singleShot(1500, check_stress_backend)

        def on_quit():
            stop_stress(stress_process)

        app.aboutToQuit.connect(on_quit)
        sys.exit(getattr(app, "exec")())