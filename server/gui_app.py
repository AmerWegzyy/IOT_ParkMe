import threading
from queue import SimpleQueue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# --- Mock imports for context ---
try:
    from utils.paths import get_logs_dir, get_models_dir, get_plots_dir, get_midi_dir, get_research_dir, get_app_root
    from utils.plotter import _elapsed_to_seconds, LivePlotter, generate_post_session_plot
    from utils.process_manager import SubprocessManager
    from utils.comms import send_calibration_command
except ImportError:
    send_calibration_command = None
    pass


try:
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ==================================================================================
# GUI APPLICATION
# This class handles the window, buttons, and layout using Tkinter.
# ==================================================================================


# --- HELPER CLASS FOR COLLAPSIBLE SECTIONS ---
class CollapsiblePane(ttk.Frame):
    def __init__(self, parent, title="", expanded=False, style_prefix=""):
        super().__init__(parent, style="Card.TFrame")
        self.parent = parent
        self.expanded = expanded
        self.title = title
        
        # Toggle Button with improved styling
        self.toggle_btn = ttk.Button(self, text=self._get_title(), command=self.toggle, 
                                     style="Compact.TButton")
        self.toggle_btn.pack(fill="x", pady=(0, 5))
        
        # Content Frame (Hidden by default)
        self.content_frame = ttk.Frame(self, style="Card.TFrame")
        
        if expanded:
            self.content_frame.pack(fill="x", expand=True, pady=(5, 0))

    def _get_title(self):
        arrow = "▼" if self.expanded else "▶"
        return f"{arrow}  {self.title}"

    def toggle(self):
        self.expanded = not self.expanded
        self.toggle_btn.configure(text=self._get_title())
        if self.expanded:
            self.content_frame.pack(fill="x", expand=True, pady=(5, 0))
        else:
            self.content_frame.pack_forget()


class GuiApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Brain-Music Interface")
        root.geometry("1100x850")
        
        # --- THEME CONFIGURATION ---
        # Define both light and dark themes
        self.theme_mode = "dark"  # Default to dark mode
        self.themes = {
            "dark": {
                "bg": "#0a0e27", "card_bg": "#141b3a", "input_bg": "#070b1a",
                "text_main": "#ffffff", "text_sub": "#8b92b8", "text_input": "#e2e8f0",
                "accent": "#6366f1", "accent_hover": "#4f46e5",
                "danger": "#ef4444", "success": "#10b981", "warning": "#f59e0b",
                "border": "#0a0e27", "shadow": "#050812", "highlight": "#2a3454",
                "plot_bg": "#1a2341",
            },
            "light": {
                "bg": "#e8ecf4", "card_bg": "#ffffff", "input_bg": "#f8fafc",
                "text_main": "#0f172a", "text_sub": "#64748b", "text_input": "#0f172a",
                "accent": "#6366f1", "accent_hover": "#4f46e5",
                "danger": "#ef4444", "success": "#10b981", "warning": "#f59e0b",
                "border": "#cbd5e1", "shadow": "#94a3b8", "highlight": "#dbeafe",
                "plot_bg": "#fafbfc",
            }
        }
        self.P = self.themes[self.theme_mode]
        root.configure(bg=self.P["bg"])

        # --- STYLE SETUP ---
        # Enhanced professional styling
        style = ttk.Style()
        try: style.theme_use("clam")
        except: pass
        
        # Base styles
        style.configure(".", background=self.P["bg"], foreground=self.P["text_main"], font=("Segoe UI", 10))
        style.configure("TFrame", background=self.P["bg"], relief="flat", borderwidth=0, highlightthickness=0)
        style.configure("Card.TFrame", background=self.P["card_bg"], relief="flat", borderwidth=0, highlightthickness=0)
        
        # Typography - Enhanced hierarchy
        style.configure("H1.TLabel", font=("Segoe UI", 24, "bold"), foreground=self.P["text_main"], background=self.P["bg"])
        style.configure("CardHeader.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.P["accent"], background=self.P["card_bg"], 
                       padding=(0, 5))
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground=self.P["text_sub"], background=self.P["bg"])
        style.configure("CardLabel.TLabel", background=self.P["card_bg"], foreground=self.P["text_main"], font=("Segoe UI", 10))
        style.configure("NavStatus.TLabel", background=self.P["bg"], foreground=self.P["accent"], font=("Segoe UI", 10, "bold"))
        
        # Button styles - More professional with better spacing
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), background=self.P["accent"], 
                       foreground="white", borderwidth=0, focuscolor=self.P["accent"], padding=(20, 14))
        style.map("Primary.TButton", background=[("active", self.P["accent_hover"]), ("disabled", "#3b3f5c")])
        
        style.configure("Danger.TButton", font=("Segoe UI", 11, "bold"), background=self.P["danger"], 
                       foreground="white", borderwidth=0, padding=(20, 14))
        style.map("Danger.TButton", background=[("active", "#dc2626"), ("disabled", "#3b3f5c")])
        
        style.configure("Secondary.TButton", font=("Segoe UI", 11, "bold"), background="#475569", 
                       foreground="white", borderwidth=0, padding=(20, 14))
        style.map("Secondary.TButton", background=[("active", "#334155"), ("disabled", "#3b3f5c")])
        
        style.configure("Success.TButton", font=("Segoe UI", 11, "bold"), background=self.P["success"], 
                       foreground="white", borderwidth=0, padding=(20, 14))
        style.map("Success.TButton", background=[("active", "#059669"), ("disabled", "#3b3f5c")])
        
        style.configure("Info.TButton", font=("Segoe UI", 11, "bold"), background="#3b82f6", 
                       foreground="white", borderwidth=0, padding=(20, 14))
        style.map("Info.TButton", background=[("active", "#2563eb"), ("disabled", "#3b3f5c")])
        
        style.configure("Compact.TButton", background=self.P["input_bg"], foreground=self.P["text_input"], 
                       borderwidth=0, padding=(10, 6), font=("Segoe UI", 9))
        style.map("Compact.TButton", background=[("active", "#e5e7eb")])
        
        style.configure("CompactPrimary.TButton", font=("Segoe UI", 9, "bold"), background=self.P["accent"], 
                       foreground="white", borderwidth=0, padding=(10, 6))
        style.map("CompactPrimary.TButton", background=[("active", self.P["accent_hover"])])
        
        style.configure("Help.TButton", font=("Segoe UI", 9, "bold"), background=self.P["card_bg"], 
                       foreground=self.P["accent"], borderwidth=0, padding=(4, 2))
        style.map("Help.TButton", background=[("active", self.P["highlight"])], foreground=[("active", "white")])
        
        # Theme toggle button - integrated with navbar
        style.configure("Theme.TButton", font=("Segoe UI", 16), background=self.P["bg"], 
                       foreground=self.P["text_main"], borderwidth=0, padding=(8, 6))
        style.map("Theme.TButton", background=[("active", self.P["highlight"])], 
                 foreground=[("active", self.P["accent"])])

        # Input styles - Clean and modern with no outlines
        style.configure("TEntry", 
                       fieldbackground=self.P["input_bg"], 
                       foreground=self.P["text_input"], 
                       padding=8, 
                       borderwidth=0, 
                       relief="flat", 
                       highlightthickness=0,
                       insertcolor=self.P["text_input"],
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"],
                       focuscolor="")
        style.map("TEntry",
                 fieldbackground=[("focus", self.P["input_bg"])],
                 bordercolor=[("focus", self.P["card_bg"])],
                 lightcolor=[("focus", self.P["card_bg"])],
                 darkcolor=[("focus", self.P["card_bg"])])
        
        style.configure("TCombobox", 
                       fieldbackground=self.P["input_bg"], 
                       foreground=self.P["text_input"], 
                       background=self.P["card_bg"], 
                       padding=5, 
                       borderwidth=0, 
                       arrowsize=15, 
                       relief="flat", 
                       highlightthickness=0,
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"],
                       focuscolor="",
                       insertwidth=0)
        style.map("TCombobox", 
                 fieldbackground=[("readonly", self.P["input_bg"])], 
                 foreground=[("readonly", self.P["text_input"])],
                 background=[("readonly", self.P["card_bg"])],
                 bordercolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 lightcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 darkcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])])
        
        # Radio buttons
        style.configure("TRadiobutton", background=self.P["card_bg"], foreground=self.P["text_main"], 
                       font=("Segoe UI", 10), padding=8,
                       borderwidth=0, relief="flat", highlightthickness=0)
        style.map("TRadiobutton", indicatorcolor=[("selected", self.P["accent"])], 
                 background=[("active", self.P["card_bg"])])

        # Checkbutton styles
        style.configure("TCheckbutton", background=self.P["bg"], foreground=self.P["text_main"], 
                       font=("Segoe UI", 10), padding=5,
                       borderwidth=0, relief="flat", highlightthickness=0)
        style.map("TCheckbutton", indicatorcolor=[("selected", self.P["accent"])],
                 background=[("active", self.P["bg"])])

        # Other components - all borderless
        style.configure("TPanedwindow", background=self.P["bg"], borderwidth=0, relief="flat")
        style.configure("TSeparator", background=self.P["border"])
        style.configure("CardSub.TLabel", font=("Segoe UI", 9), foreground=self.P["text_sub"], 
                       background=self.P["card_bg"])
        
        # Treeview - completely borderless
        style.configure("Treeview", background=self.P["card_bg"], foreground=self.P["text_main"],
                       fieldbackground=self.P["card_bg"], borderwidth=0, rowheight=30,
                       relief="flat", highlightthickness=0,
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"])
        style.configure("Treeview.Heading",
                       background=self.P["card_bg"],
                       foreground=self.P["text_main"],
                       borderwidth=0,
                       relief="flat")
        style.map("Treeview", background=[("selected", self.P["accent"])], foreground=[("selected", "white")])
        
        # Progressbar
        style.configure("TProgressbar", troughcolor=self.P["border"], background=self.P["accent"], 
                       borderwidth=0, thickness=8)
        
        # Scale (Slider) styling
        style.configure("TScale", background=self.P["card_bg"], troughcolor=self.P["border"], 
                       borderwidth=0, sliderlength=25, sliderrelief="flat")
        
        # Scrollbar styling - make it blend in
        style.configure("Vertical.TScrollbar", 
                       background=self.P["card_bg"],
                       troughcolor=self.P["card_bg"],
                       borderwidth=0,
                       arrowsize=0,
                       relief="flat")
        style.configure("Horizontal.TScrollbar", 
                       background=self.P["card_bg"],
                       troughcolor=self.P["card_bg"],
                       borderwidth=0,
                       arrowsize=0,
                       relief="flat")

        base_dir = get_midi_dir()
        default_midi = base_dir / "Technion_March1.mid"
        
        self.session_thread = None
        self.status_queue = SimpleQueue()
        self.session_dir_queue = SimpleQueue()
        self.data_queue = SimpleQueue()
        self.current_session_dir = None
        self.live_data_buffer = []
        # Limit how many points we render per frame (buffer keeps full history)
        self.max_live_points = 2500
        # Sliding window controls
        self.view_window_sec = 240  # visible time window for live plot
        self.buffer_cap = 30000     # absolute cap to avoid unbounded growth
        # Live plot uses subplots_adjust; avoid tight_layout in the hot path for FPS stability.
        self._did_tight_layout = True
        self.is_running = False
        self.is_calibrating = False
        self.is_app_active = True
        # Poll jobs
        self.job_status = None
        self.job_dir = None
        self.job_plot = None
        self.job_ports = None
        
        self.port_scan_thread = None

        # Registry for scrollable canvases (for smart mousewheel routing)
        self.scrollable_canvases = []
        
        # Initialize mode-specific variables (created properly in Mode Settings tab later)
        self.random_span_display_var = tk.DoubleVar(value=20.0)
        self.rnd_val_str = tk.StringVar(value="20")
        self.gamify_var = tk.BooleanVar(value=False)
        self.random_simple_threshold_var = tk.StringVar(value="5.0")
        self.random_simple_steps_var = tk.StringVar(value="5")
        self.random_simple_timeout_var = tk.StringVar(value="15.0")
        self.hybrid_lock_var = tk.StringVar(value="5")
        self.hybrid_unlock_var = tk.StringVar(value="1.5")
        self.hybrid_stability_var = tk.StringVar(value="3.0")
        self.hybrid_unlock_thres_var = tk.StringVar(value="5.0")

    # --- LAYOUT ---
        # Enhanced navbar with gradient-like effect
        navbar = ttk.Frame(root, style="TFrame")
        navbar.pack(fill="x", padx=30, pady=(25, 15))
        
        title_box = ttk.Frame(navbar, style="TFrame")
        title_box.pack(side="left")
        
        # Add subtle icon/branding
        header_frame = ttk.Frame(title_box, style="TFrame")
        header_frame.pack(anchor="w")
        ttk.Label(header_frame, text="🧠", style="H1.TLabel", font=("Segoe UI", 32)).pack(side="left", padx=(0, 12))
        title_text_frame = ttk.Frame(header_frame, style="TFrame")
        title_text_frame.pack(side="left")
        ttk.Label(title_text_frame, text="BRAIN SYNC", style="H1.TLabel").pack(anchor="w")
        ttk.Label(title_text_frame, text="Neuro-Adaptive Music Controller", style="Sub.TLabel", 
                 font=("Segoe UI", 11)).pack(anchor="w", pady=(2, 0))
        
        # Status area with improved styling
        status_box = ttk.Frame(navbar, style="TFrame")
        status_box.pack(side="right", anchor="e")
        
        # Theme toggle button with better styling
        theme_icon = "☀" if self.theme_mode == "dark" else "☾"
        self.theme_btn = ttk.Button(status_box, text=theme_icon, command=self.toggle_theme, 
                                     style="Theme.TButton", width=3)
        self.theme_btn.pack(side="left", padx=(0, 15))
        
        # Status label with background card
        status_card = ttk.Frame(status_box, style="Card.TFrame", padding=(12, 8))
        status_card.pack(side="left", padx=(0, 15))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_card, textvariable=self.status_var, style="NavStatus.TLabel").pack()
        
        # LED indicators with improved design
        self.led_canvas = tk.Canvas(status_box, width=120, height=40, bg=self.P["bg"], highlightthickness=0, bd=0)
        self.led_canvas.pack(side="left")
        self.led_sys = self._draw_led(90, 20, "System", self.P["success"])
        self.led_run = self._draw_led(20, 20, "Active", self.P["border"])
        
        main_body = ttk.Frame(root, style="TFrame")
        main_body.pack(fill="both", expand=True, padx=30, pady=(0, 20))
        main_body.columnconfigure(0, weight=0, minsize=360)
        main_body.columnconfigure(1, weight=1)
        main_body.rowconfigure(0, weight=1)

        # Sidebar Container with enhanced card styling
        sidebar_container = ttk.Frame(main_body, style="Card.TFrame")
        sidebar_container.grid(row=0, column=0, sticky="nsew", padx=(0, 25))
        
        # Create Canvas WITHOUT scrollbar (autohide when not needed)
        self.canvas_sidebar = tk.Canvas(sidebar_container, bg=self.P["card_bg"], highlightthickness=0, 
                                       bd=0, relief="flat")
        # Scrollbar styled to blend in (only visible on hover via OS)
        scrollbar = ttk.Scrollbar(sidebar_container, orient="vertical", command=self.canvas_sidebar.yview, 
                                 style="Vertical.TScrollbar")
        
        # The actual Frame inside the canvas with better padding
        sidebar = ttk.Frame(self.canvas_sidebar, style="Card.TFrame", padding=25)
        
        # Logic to make the frame inside the canvas scrollable
        sidebar.bind(
            "<Configure>",
            lambda e: self.canvas_sidebar.configure(
                scrollregion=self.canvas_sidebar.bbox("all")
            )
        )
        
        self.canvas_sidebar.create_window((0, 0), window=sidebar, anchor="nw", tags="inner_frame")
        self.canvas_sidebar.configure(yscrollcommand=scrollbar.set)
        
        self.canvas_sidebar.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Register this canvas for smart mousewheel routing
        self.scrollable_canvases.append(('sidebar', self.canvas_sidebar, sidebar))
        
        # Fix width of inner frame to match canvas
        def _configure_canvas(event):
            self.canvas_sidebar.itemconfig("inner_frame", width=event.width)
        self.canvas_sidebar.bind("<Configure>", _configure_canvas)
        
        def section(title): 
            if sidebar.winfo_children():  # Add separator before sections (except first)
                ttk.Separator(sidebar, orient="horizontal").pack(fill="x", pady=(20, 0))
            ttk.Label(sidebar, text=title.upper(), style="CardHeader.TLabel").pack(anchor="w", pady=(20, 10))

        # MIDI Track Selection with improved spacing
        section("MIDI Track")
        midi_row = ttk.Frame(sidebar, style="Card.TFrame")
        midi_row.pack(fill="x", pady=(0, 5))
        
        self.midi_var = tk.StringVar(value=str(default_midi.name))
        self.midi_combo = ttk.Combobox(midi_row, textvariable=self.midi_var, font=("Segoe UI", 10))
        self.midi_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        ttk.Button(midi_row, text="📂", style="Compact.TButton", width=4, command=self.choose_midi).pack(side="right")
        
        # SESSION NAME SELECTOR
        section("Session Name")
        self.session_row = ttk.Frame(sidebar, style="Card.TFrame")
        self.session_row.pack(fill="x", pady=(0, 5))
        
        self.session_name_var = tk.StringVar()
        self.session_input_widget = ttk.Combobox(self.session_row, textvariable=self.session_name_var, 
                                                 font=("Segoe UI", 10))
        self.session_input_widget.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        ttk.Button(self.session_row, text="🔄", style="Compact.TButton", width=4, 
                  command=self.refresh_session_list).pack(side="right")
        
        # SERIAL PORT
        section("Serial Port")
        port_row = ttk.Frame(sidebar, style="Card.TFrame")
        port_row.pack(fill="x", pady=(0, 5))
        
        self.port_var = tk.StringVar(value="COM3")
        
        if SERIAL_AVAILABLE:
            self.port_combo = ttk.Combobox(port_row, textvariable=self.port_var, font=("Segoe UI", 10))
            self.port_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Button(port_row, text="🔄", style="Compact.TButton", width=4, 
                      command=self.refresh_ports).pack(side="right")
        else:
            ttk.Entry(port_row, textvariable=self.port_var, font=("Segoe UI", 10)).pack(fill="x", expand=True)

        # Sync Mode with improved radio button styling
        section("Sync Mode")
        mode_container = ttk.Frame(sidebar, style="Card.TFrame")
        mode_container.pack(fill="x", pady=(0, 5))
        
        self.mode_var = tk.StringVar(value="dynamic")
        ttk.Radiobutton(mode_container, text="🧠  Dynamic Sync", value="dynamic", 
                       variable=self.mode_var, command=self.on_mode_change).pack(anchor="w", pady=6)
        ttk.Radiobutton(mode_container, text="🚀  Hybrid Mode", value="hybrid", 
                       variable=self.mode_var, command=self.on_mode_change).pack(anchor="w", pady=6)
        ttk.Radiobutton(mode_container, text="🎲  Random Mode", value="random", 
                       variable=self.mode_var, command=self.on_mode_change).pack(anchor="w", pady=6)
        ttk.Radiobutton(mode_container, text="🛠  Manual Override", value="manual", 
                       variable=self.mode_var, command=self.on_mode_change).pack(anchor="w", pady=6)
        
        # MANUAL BPM with improved design
        section("Target BPM")
        self.manual_bpm_frame = ttk.Frame(sidebar, style="TFrame")
        self.manual_bpm_frame.pack(fill="x", pady=(0, 5))
        
        # BPM value display with better styling
        self.manual_bpm_var = tk.DoubleVar(value=100.0)
        
        self.bpm_val_label = ttk.Label(self.manual_bpm_frame, text="100 BPM", 
                                       font=("Segoe UI", 16, "bold"), foreground=self.P["text_main"],
                                       background=self.P["bg"])
        self.bpm_val_label.pack(pady=(0, 8))
        
        # BPM Slider with custom styling
        bpm_slider_frame = ttk.Frame(self.manual_bpm_frame, style="TFrame")
        bpm_slider_frame.pack(fill="x", pady=(0, 5))
        
        self.bpm_slider = ttk.Scale(bpm_slider_frame, from_=0, to=400, orient="horizontal", 
                                   variable=self.manual_bpm_var, command=self.on_bpm_slider_change,
                                   length=280)
        self.bpm_slider.pack(fill="x", padx=5)

        # Initialize variables for Analysis tab
        self.subject_var = tk.StringVar()
        self.session_var = tk.StringVar()
        
        # --- STARTUP MODE ---
        section("Startup Mode")
        startup_container = ttk.Frame(sidebar, style="Card.TFrame")
        startup_container.pack(fill="x", pady=(0, 5))
        
        self.startup_mode_var = tk.StringVar(value="music_first")
        ttk.Radiobutton(startup_container, text="🎵  Music First (Default BPM)", 
                       value="music_first", variable=self.startup_mode_var,
                       command=self.on_startup_mode_change).pack(anchor="w", pady=6)
        ttk.Radiobutton(startup_container, text="🚶  Walk First (Detected BPM)", 
                       value="walk_first", variable=self.startup_mode_var,
                       command=self.on_startup_mode_change).pack(anchor="w", pady=6)
        
        # Walk steps count input (only shown when walk_first is selected)
        self.walk_steps_frame = ttk.Frame(sidebar, style="Card.TFrame")
        walk_steps_row = ttk.Frame(self.walk_steps_frame, style="Card.TFrame")
        walk_steps_row.pack(fill="x", pady=(5, 0))
        
        ttk.Label(walk_steps_row, text="Calibration Steps:", 
                 style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left", padx=(10, 5))
        self.walk_steps_var = tk.StringVar(value="10")
        ttk.Entry(walk_steps_row, textvariable=self.walk_steps_var, 
                 width=8, font=("Segoe UI", 10)).pack(side="left", padx=(0, 5))
        ttk.Label(walk_steps_row, text="steps", 
                 style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        # Initially hidden
        
        # --- INFO ABOUT MODE SETTINGS TAB ---
        info_frame = ttk.Frame(sidebar, style="Card.TFrame", padding=10)
        info_frame.pack(fill="x", pady=(15, 0))
        ttk.Label(info_frame, text="💡 Tip:", style="CardLabel.TLabel", 
                 font=("Segoe UI", 9, "bold"), foreground=self.P["accent"]).pack(anchor="w")
        ttk.Label(info_frame, text="Advanced mode settings\n(Random, Hybrid, etc.) can be\nconfigured in the Mode Settings tab", 
                 style="CardSub.TLabel", font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))
        
        # --- BOTTOM CONTROLS ---
        ttk.Frame(sidebar, style="Card.TFrame").pack(fill="both", expand=True) # Spacer pushes everything down

        section("Session Control")
        
        # Primary action buttons with enhanced styling
        self.btn_start = ttk.Button(sidebar, text="▶  START SESSION", command=self.start_session, 
                                     style="Primary.TButton")
        self.btn_start.pack(fill="x", pady=(0, 12))
        
        self.btn_stop = ttk.Button(sidebar, text="⏹  STOP SESSION", command=self.stop_session, 
                                    style="Danger.TButton", state="disabled")
        self.btn_stop.pack(fill="x", pady=(0, 12))
        
        self.btn_calibrate = ttk.Button(sidebar, text="✅  CALIBRATE WEIGHT", command=self.on_calibrate_weight, 
                                         style="Success.TButton")
        self.btn_calibrate.pack(fill="x", pady=(0, 12))

        self.btn_quit = ttk.Button(sidebar, text="❌  QUIT APPLICATION", command=self.quit_app, 
                                    style="Secondary.TButton")
        self.btn_quit.pack(fill="x")

        # ====================== TABBED MAIN AREA ======================
        # Notebook for switching between Session (live plot) and Training tabs
        self.main_notebook = ttk.Notebook(main_body)
        self.main_notebook.grid(row=0, column=1, sticky="nsew")

        # Configure Notebook style with enhanced tabs - completely borderless
        style.configure("TNotebook", 
                       background=self.P["bg"], 
                       borderwidth=0, 
                       relief="flat", 
                       highlightthickness=0,
                       bordercolor=self.P["bg"],
                       lightcolor=self.P["bg"],
                       darkcolor=self.P["bg"],
                       tabmargins=[0, 0, 0, 0])
        # Remove ALL border elements from the notebook
        style.layout("TNotebook", [
            ("Notebook.client", {"sticky": "nswe", "border": 0})
        ])
        style.layout("TNotebook.Tab", [
            ("Notebook.tab", {
                "sticky": "nswe",
                "children": [
                    ("Notebook.padding", {
                        "side": "top",
                        "sticky": "nswe",
                        "children": [
                            ("Notebook.label", {"side": "top", "sticky": ""})
                        ]
                    })
                ]
            })
        ])
        style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"), padding=(20, 12),
                        background=self.P["border"], foreground=self.P["text_sub"],
                        borderwidth=0, relief="flat",
                        focuscolor="",
                        lightcolor=self.P["bg"],
                        darkcolor=self.P["bg"],
                        bordercolor=self.P["bg"])
        style.map("TNotebook.Tab",
                  background=[("selected", self.P["accent"])],
                  foreground=[("selected", "white")],
                  lightcolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])],
                  darkcolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])],
                  bordercolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])],
                  expand=[("selected", (1, 1, 1, 0))])

        # -------------------- TAB 1: SESSION (Live Plot) --------------------
        tab_session = ttk.Frame(self.main_notebook, style="TFrame")
        self.main_notebook.add(tab_session, text="  ▶  Live Session  ")

        # Visualization controls with better styling
        viz_controls = ttk.Frame(tab_session, style="TFrame")
        viz_controls.pack(fill="x", pady=(10, 10))
        
        ttk.Label(viz_controls, text="Display Options:", style="Sub.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(10, 20))
        
        self.show_2x_var = tk.BooleanVar(value=False)
        self.show_half_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(viz_controls, text="Show 2x BPM Reference", variable=self.show_2x_var, 
                        command=self.update_plot_options).pack(side="right", padx=15)
        ttk.Checkbutton(viz_controls, text="Show 0.5x BPM Reference", variable=self.show_half_var, 
                        command=self.update_plot_options).pack(side="right", padx=15)
        
        # Plot card with enhanced styling
        plot_card = ttk.Frame(tab_session, style="Card.TFrame", padding=15)
        plot_card.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.figure.patch.set_facecolor(self.P.get("plot_bg", self.P["card_bg"]))
        self.ax1 = self.figure.add_subplot(111)
        self.ax2 = None
        self.figure.subplots_adjust(left=0.08, bottom=0.1, right=0.95, top=0.92)
        
        self.plotter = LivePlotter(self.ax1, self.P)
        self.plotter.view_window_sec = self.view_window_sec
        self.plotter.update(pd.DataFrame({"seconds": [], "walking_bpm": [], "song_bpm": [], "step_event": []}))

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_card)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.configure(borderwidth=0, highlightthickness=0, relief="flat")
        canvas_widget.pack(fill="both", expand=True)
        
        # Notification Label (Top-right overlay) - Initially hidden
        self.notification_label = tk.Label(
            tab_session, 
            text="",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg=self.P["warning"],
            padx=15,
            pady=10,
            relief="solid",
            borderwidth=2
        )

        # -------------------- TAB 2: MODEL TRAINING --------------------
        tab_training = ttk.Frame(self.main_notebook, style="TFrame")
        self.main_notebook.add(tab_training, text="  🧠  Model Training  ")
        self._build_training_tab(tab_training)

        # -------------------- TAB 3: ANALYSIS --------------------
        tab_analysis = ttk.Frame(self.main_notebook, style="TFrame")
        self.main_notebook.add(tab_analysis, text="  📊  Analysis  ")
        self._build_analysis_tab(tab_analysis)

        # -------------------- TAB 4: MODE SETTINGS --------------------
        tab_mode_settings = ttk.Frame(self.main_notebook, style="TFrame")
        self.main_notebook.add(tab_mode_settings, text="  ⚙  Mode Settings  ")
        self._build_mode_settings_tab(tab_mode_settings)

        self.on_mode_change() # Init state
        self.poll_status()
        self.poll_session_dir()
        self.poll_status()
        self.poll_session_dir()
        self.poll_plot()
        self.poll_plot()
        if SERIAL_AVAILABLE:
            self.poll_ports() # Auto refresh ports
            
        self.refresh_session_list() # Init session list
        self.refresh_midi_list()    # Init MIDI list
        
        # Setup global smart mousewheel routing
        self._setup_smart_mousewheel()

    def _setup_smart_mousewheel(self):
        """Setup intelligent mousewheel routing based on cursor position"""
        def smart_mousewheel(event):
            # Get the widget under the mouse
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
            widget = self.root.winfo_containing(x, y)
            
            if not widget:
                return
            
            # Check which scrollable canvas hierarchy the widget belongs to
            for name, canvas, container in self.scrollable_canvases:
                # Walk up the widget hierarchy to see if we're inside this canvas
                current = widget
                while current:
                    if current == canvas or current == container:
                        # Found it! Scroll this canvas
                        try:
                            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                        except:
                            pass
                        return
                    try:
                        current = current.master
                    except:
                        break
        
        # Bind globally but route smartly
        self.root.bind_all("<MouseWheel>", smart_mousewheel)

    def _draw_led(self, x, y, l, c):
        """Draw an LED indicator with enhanced styling"""
        r=7
        # Add subtle glow effect
        self.led_canvas.create_oval(x-r-2, y-r-2, x+r+2, y+r+2, fill=self.P["shadow"], outline="")
        o=self.led_canvas.create_oval(x-r, y-r, x+r, y+r, fill=c, outline=self.P["highlight"], width=1)
        self.led_canvas.create_text(x+18, y, text=l, anchor="w", fill=self.P["text_sub"], 
                                    font=("Segoe UI", 9, "bold"))
        return o

    def _set_led(self, i, a, c=None): 
        """Update LED state with color"""
        self.led_canvas.itemconfig(i, fill=(c if c else self.P["success"]) if a else self.P["border"])

    def log(self, msg): self.status_var.set(msg)
    def choose_midi(self): 
        p = filedialog.askopenfilename(filetypes=[("MIDI", ".mid"), ("All", ".*")])
        if p: self.midi_var.set(p)

    def refresh_ports(self):
        """Populate the combobox with detected serial ports."""
        if not SERIAL_AVAILABLE: return
        ports = serial.tools.list_ports.comports()
        values = [f"{p.device} - {p.description}" for p in ports]
        self.port_combo['values'] = values
        if values:
            self.port_combo.current(0)
        else:
            self.port_combo.set("No devices found")
            
    def get_midi_files(self):
        """Scans midi_files/ directory."""
        try:
            return [f.name for f in get_midi_dir().glob("*.mid")]
        except: return []

    def refresh_midi_list(self):
        self.midi_combo['values'] = self.get_midi_files()
        if self.midi_combo['values']: self.midi_combo.current(0)

    def _refresh_model_list(self):
        """Scan for available prediction models (base + user heads)."""
        models_dir = get_models_dir()
        model_options = []
        self._model_paths = {}  # Map display name -> actual path
        
        # Base model
        base_model = models_dir / "lgbm_model.joblib"
        if base_model.exists():
            model_options.append("Base Model")
            self._model_paths["Base Model"] = str(base_model)
        
        # User head models
        for head in sorted(models_dir.glob("lgbm_user_head_*.joblib")):
            suffix = head.stem.replace("lgbm_user_head_", "")
            display_name = f"User Head: {suffix}"
            model_options.append(display_name)
            self._model_paths[display_name] = str(head)
        
        if not model_options:
            model_options = ["No models found"]
            self._model_paths["No models found"] = None
        
        self.model_combo['values'] = model_options
        if model_options and self.model_var.get() not in model_options:
            self.model_combo.current(0)

    def get_selected_model_path(self):
        """Return the file path of the selected prediction model, or None."""
        selected = self.model_var.get()
        return self._model_paths.get(selected)
    
    def on_bpm_slider_change(self, val):
        """Handle slider movement with real-time update."""
        bpm = float(val)
        # Update the BPM label display
        self.bpm_val_label.configure(text=f"{int(bpm)} BPM")
        
        # If in manual mode and running, update immediately
        if self.mode_var.get() == "manual":
            if self.session_thread: 
                self.session_thread.update_manual_bpm(bpm)
            # We don't log every single slide event to avoid spam

    def on_bpm_entry(self, event=None):
        """Handle BPM entry."""
        try:
             bpm = float(self.bpm_str.get())
             bpm = max(0, min(400, bpm))
             self.manual_bpm_var.set(bpm)
             self.on_bpm_slider_change(bpm)
        except ValueError:
             self.bpm_str.set(f"{int(self.manual_bpm_var.get())}")
            
    def on_random_slider_change(self, val):
        """Update entry and backend when slider moves."""
        display_value = float(val)  # 1-100
        actual_value = display_value / 100.0  # Convert to 0.01-1.00
        
        self.rnd_val_str.set(f"{int(display_value)}")
        
        if self.mode_var.get() == "random" and self.session_thread:
             self.session_thread.update_random_span(actual_value)

    def on_gui_sync(self, key, value):
        """Called by SubprocessManager when backend sends a sync packet."""
        try:
            if key == "MANUAL_BPM":
                bpm = float(value)
                # Update without triggering another command (idempotent anyway)
                self.manual_bpm_var.set(bpm)
                self.bpm_str.set(f"{int(bpm)}")
                # If we were using the slider value directly for display, we're good.
        except: pass

    def on_random_span_entry(self, event=None):
        """Update slider and backend when entry changes."""
        try:
             display_value = float(self.rnd_val_str.get())  # User enters 1-100
             # Clamp to 1-100
             display_value = max(1, min(100, display_value))
             actual_value = display_value / 100.0  # Convert to 0.01-1.00
             
             self.random_span_display_var.set(display_value)  # Move slider
             self.rnd_val_str.set(f"{int(display_value)}")  # Format nicely
             
             if self.mode_var.get() == "random" and self.session_thread:
                 self.session_thread.update_random_span(actual_value)
        except ValueError:
             # Reset to slider value if invalid
             self.rnd_val_str.set(f"{int(self.random_span_display_var.get())}")
            
    def get_selected_port(self):
        val = self.port_var.get() if not SERIAL_AVAILABLE else self.port_combo.get()
        return val.split(" - ")[0] if " - " in val else val

    def validate_number(self, new_value):
        """Allow only numeric input."""
        if new_value == "": return True
        try:
            float(new_value)
            return True
        except ValueError:
            return False

    def _set_frame_state(self, frame, state):
        """Recursively set state for all widgets in a frame."""
        try: frame.configure(state=state)
        except: pass
        for child in frame.winfo_children():
            try: child.configure(state=state)
            except: pass
            # Recurse for nested frames
            if isinstance(child, ttk.Frame):
                self._set_frame_state(child, state)

    def on_mode_change(self):
        m = self.mode_var.get()
        
        # Enable/disable manual BPM slider based on mode
        manual_state = "normal" if m == "manual" else "disabled"
        self._set_frame_state(self.manual_bpm_frame, manual_state)
        
        # Switch Mode on Backend (if session is running)
        if not self.session_thread:
            return
            
        if m == "manual":
            self.session_thread.set_manual_mode(True)
            # Apply current BPM immediately if switching to manual
            val = self.manual_bpm_var.get()
            self.on_bpm_slider_change(val)
            
        elif m == "random":
            self.session_thread.set_random_mode(True)
            # Apply random span & gamify (convert display value 1-100 to actual 0.01-1.00)
            display_val = self.random_span_display_var.get()
            actual_val = display_val / 100.0
            self.session_thread.update_random_span(actual_val)
            self.session_thread.update_random_gamified(self.gamify_var.get())
            # Sync simple mode settings
            self.session_thread.update_random_simple_threshold(float(self.random_simple_threshold_var.get()))
            self.session_thread.update_random_simple_steps(int(self.random_simple_steps_var.get()))
            self.session_thread.update_random_simple_timeout(float(self.random_simple_timeout_var.get()))
        
        elif m == "hybrid":
            self.session_thread.set_hybrid_mode(True)
            # Apply current hybrid settings from GUI
            self.session_thread.update_hybrid_lock_steps(int(self.hybrid_lock_var.get()))
            self.session_thread.update_hybrid_unlock_time(float(self.hybrid_unlock_var.get()))
            self.session_thread.update_hybrid_stability_threshold(float(self.hybrid_stability_var.get()))
            self.session_thread.update_hybrid_unlock_threshold(float(self.hybrid_unlock_thres_var.get()))
            
        else: # dynamic
            self.session_thread.set_dynamic_mode(True)
             
    def on_gamify_toggle(self):
        """Called when gamify checkbox is toggled."""
        is_gamified = self.gamify_var.get()
        if is_gamified:
            self.lbl_match_steps_header.configure(text="Match Hold Time")
            self.lbl_match_steps_desc.configure(text="Hold target BPM for duration to match")
            self.lbl_match_steps_sub.configure(text="seconds (5-100)")
        else:
            self.lbl_match_steps_header.configure(text="Match Steps")
            self.lbl_match_steps_desc.configure(text="Consecutive steps within threshold to hit target")
            self.lbl_match_steps_sub.configure(text="steps (5-100)")
            
        if self.session_thread:
            self.session_thread.update_random_gamified(is_gamified)
            # Send current values to ensure the backend uses the right mapping immediately
            self.session_thread.update_random_simple_threshold(self.random_simple_threshold_var.get())
            self.session_thread.update_random_simple_steps(self.random_simple_steps_var.get())
            self.session_thread.update_random_simple_timeout(self.random_simple_timeout_var.get())

    def on_random_simple_threshold_change(self, event=None):
        """Called when random simple threshold is changed."""
        try:
            original = self.random_simple_threshold_var.get().strip()
            if not original:
                return
            bpm = float(original)
            
            # Clamp to valid range
            if bpm < 1.0:
                self.log(f"⚠ Match Threshold too low: {bpm:.1f} → 1.0 (minimum)")
                self.random_simple_threshold_var.set("1.0")
                bpm = 1.0
            elif bpm > 20.0:
                self.log(f"⚠ Match Threshold too high: {bpm:.1f} → 20.0 (maximum)")
                self.random_simple_threshold_var.set("20.0")
                bpm = 20.0
            
            if self.session_thread:
                self.session_thread.update_random_simple_threshold(bpm)
            self.log(f"✓ Random Match Threshold: {bpm:.1f} BPM")
        except ValueError:
            if original:
                self.log(f"❌ Invalid Match Threshold '{original}' - enter a number (1.0-20.0)")

    def on_random_simple_steps_change(self, event=None):
        """Called when random simple steps is changed."""
        try:
            original = self.random_simple_steps_var.get().strip()
            if not original:
                return
            steps = int(original)
            
            # Clamp to valid range
            if steps < 5:
                self.log(f"⚠ Match Steps too low: {steps} → 5 (minimum)")
                self.random_simple_steps_var.set("5")
                steps = 5
            elif steps > 100:
                self.log(f"⚠ Match Steps too high: {steps} → 100 (maximum)")
                self.random_simple_steps_var.set("100")
                steps = 100
            
            if self.session_thread:
                self.session_thread.update_random_simple_steps(steps)
            self.log(f"✓ Random Match Steps: {steps}")
        except ValueError:
            if original:
                self.log(f"❌ Invalid Match Steps '{original}' - enter a number (5-100)")

    def on_random_simple_timeout_change(self, event=None):
        """Called when random simple timeout is changed."""
        try:
            original = self.random_simple_timeout_var.get().strip()
            if not original:
                return
            sec = float(original)
            
            # Clamp to valid range
            if sec < 5.0:
                self.log(f"⚠ Timeout too low: {sec:.1f} → 5.0 (minimum)")
                self.random_simple_timeout_var.set("5.0")
                sec = 5.0
            elif sec > 300.0:
                self.log(f"⚠ Timeout too high: {sec:.1f} → 300.0 (maximum)")
                self.random_simple_timeout_var.set("300.0")
                sec = 300.0
            
            if self.session_thread:
                self.session_thread.update_random_simple_timeout(sec)
            self.log(f"✓ Random Timeout: {sec:.1f}s")
        except ValueError:
            if original:
                self.log(f"❌ Invalid Timeout '{original}' - enter a number (5.0-300.0)")

    def on_hybrid_lock_change(self, event=None):
        """Called when hybrid lock steps is changed."""
        # Only validate on Return key, not FocusOut
        if event and event.type == '10':  # FocusOut event
            return
            
        try:
            original = self.hybrid_lock_var.get().strip()
            if not original:
                return
            steps = int(original)
            
            # Clamp to valid range
            if steps < 2:
                self.log(f"⚠ Lock Steps too low: {steps} → 2 (minimum)")
                self.hybrid_lock_var.set("2")
                steps = 2
            elif steps > 20:
                self.log(f"⚠ Lock Steps too high: {steps} → 20 (maximum)")
                self.hybrid_lock_var.set("20")
                steps = 20
            
            if self.session_thread:
                self.session_thread.update_hybrid_lock_steps(steps)
            self.log(f"✓ Hybrid Lock Steps: {steps}")
        except ValueError:
            if original:  # Only complain if they actually entered something invalid
                self.log(f"❌ Invalid Lock Steps '{original}' - enter a number (2-20)")

    def on_hybrid_unlock_change(self, event=None):
        """Called when hybrid unlock time is changed (deprecated - not used)."""
        pass  # Kept for compatibility but unused

    def on_hybrid_stability_change(self, event=None):
        """Called when hybrid stability threshold is changed."""
        # Only validate on Return key, not FocusOut
        if event and event.type == '10':  # FocusOut event
            return
            
        try:
            original = self.hybrid_stability_var.get().strip()
            if not original:
                return
            bpm = float(original)
            
            # Clamp to valid range
            if bpm < 1.0:
                self.log(f"⚠ Stability Threshold too low: {bpm:.1f} → 1.0 (minimum)")
                self.hybrid_stability_var.set("1.0")
                bpm = 1.0
            elif bpm > 10.0:
                self.log(f"⚠ Stability Threshold too high: {bpm:.1f} → 10.0 (maximum)")
                self.hybrid_stability_var.set("10.0")
                bpm = 10.0
            
            if self.session_thread:
                self.session_thread.update_hybrid_stability_threshold(bpm)
            self.log(f"✓ Hybrid Stability Threshold: {bpm:.1f} BPM")
        except ValueError:
            if original:  # Only complain if they actually entered something invalid
                self.log(f"❌ Invalid Stability Threshold '{original}' - enter a number (1.0-10.0)")

    def on_hybrid_unlock_thres_change(self, event=None):
        """Called when hybrid unlock threshold is changed."""
        # Only validate on Return key, not FocusOut
        if event and event.type == '10':  # FocusOut event
            return
            
        try:
            original = self.hybrid_unlock_thres_var.get().strip()
            if not original:
                return
            bpm = float(original)
            
            # Clamp to valid range
            if bpm < 5.0:
                self.log(f"⚠ Unlock Threshold too low: {bpm:.1f} → 5.0 (minimum)")
                self.hybrid_unlock_thres_var.set("5.0")
                bpm = 5.0
            elif bpm > 50.0:
                self.log(f"⚠ Unlock Threshold too high: {bpm:.1f} → 50.0 (maximum)")
                self.hybrid_unlock_thres_var.set("50.0")
                bpm = 50.0
            
            if self.session_thread:
                self.session_thread.update_hybrid_unlock_threshold(bpm)
            self.log(f"✓ Hybrid Unlock Threshold: {bpm:.1f} BPM")
        except ValueError:
            if original:  # Only complain if they actually entered something invalid
                self.log(f"❌ Invalid Unlock Threshold '{original}' - enter a number (5.0-50.0)")

    def on_startup_mode_change(self):
        """Show/hide walk steps input based on startup mode selection."""
        if self.startup_mode_var.get() == "walk_first":
            self.walk_steps_frame.pack(fill="x", pady=(0, 10), after=self.walk_steps_frame.master.winfo_children()[self.walk_steps_frame.master.winfo_children().index(self.walk_steps_frame)-1])
        else:
            self.walk_steps_frame.pack_forget()

    def start_session(self):
        """Action for the 'START SESSION' button."""
        if self.is_running: return
        if self.is_training:
            self.log("Cannot start session while training is in progress.")
            return

        # Clear any leftover live data/plot from previous session
        self.live_data_buffer = []
        while not self.data_queue.empty():
            self.data_queue.get_nowait()
        self.plotter.reset()
        # Pre-warm renderer so the first incoming packets do not pay the initial draw cost.
        try:
            self.canvas.draw()
        except Exception:
            self.canvas.draw_idle()
        
        # Resolve MIDI Path (Dropdown Name -> Full Path)
        m_name = self.midi_var.get()
        # Check if absolute path (from file picker) or relative (from dropdown)
        if Path(m_name).exists():
            p = Path(m_name)
        else:
            # Try finding it in midi_files
            p = get_midi_dir() / m_name
            
        if not p.exists(): messagebox.showerror("Error", f"MIDI not found: {m_name}"); return
        
        port = self.get_selected_port()
        if not port or "No devices" in port:
            messagebox.showerror("Error", "Please select a valid Serial Port")
            return

        # Prepare parameters
        mm = self.mode_var.get() == "manual"
        # BPM is now from DoubleVar
        mb = self.manual_bpm_var.get() if mm else None
        
        # Session Name
        s_name = self.session_name_var.get().strip()
        if not s_name: s_name = None # Let logger generate timestamp

        try:
            raw_sw = self.step_window_var.get().strip()
            sw = int(raw_sw) if raw_sw and raw_sw.isdigit() else None  # None -> use engine default
        except:
            sw = None

        try:
            raw_st = self.stride_var.get().strip()
            st = int(raw_st) if raw_st and raw_st.isdigit() else None  # None -> use engine default
        except:
            st = None

        # Climbing/Cascading Alphas
        au = None
        try:
            val = self.smoothing_up_var.get().strip()
            if val: au = float(val)
        except: pass
        
        ad = None
        try:
            val = self.smoothing_down_var.get().strip()
            if val: ad = float(val)
        except: pass

        # Get selected prediction model path
        model_path = self.get_selected_model_path()
        
        # Get startup mode parameters
        startup_mode = self.startup_mode_var.get()
        walk_steps = None
        if startup_mode == "walk_first":
            try:
                walk_steps = int(self.walk_steps_var.get())
            except:
                walk_steps = 10  # Default
        
        # Create and start the Subprocess Manager
        self.session_thread = SubprocessManager(
            str(p),
            port,
            mm,
            mb,
            sw,
            st,
            self.enqueue_status,
            self.enqueue_session_dir,
            self.enqueue_data,
            session_name=s_name,
            alpha_up=au,
            alpha_down=ad,
            hybrid_mode=(self.mode_var.get() == "hybrid"),
            random_mode=(self.mode_var.get() == "random"),
            random_span=self.random_span_display_var.get() / 100.0,  # Convert display (1-100) to actual (0.01-1.00)
            random_gamified=self.gamify_var.get(),
            random_simple_threshold=self.random_simple_threshold_var.get(),
            random_simple_steps=self.random_simple_steps_var.get(),
            random_simple_timeout=self.random_simple_timeout_var.get(),
            hybrid_lock_steps=self.hybrid_lock_var.get(),
            hybrid_unlock_time=self.hybrid_unlock_var.get(),
            hybrid_stability_threshold=self.hybrid_stability_var.get(),
            hybrid_unlock_threshold=self.hybrid_unlock_thres_var.get(),
            gui_sync_callback=self.on_gui_sync,
            model_path=model_path,
            startup_mode=startup_mode,
            walk_steps=walk_steps,
        )
        
        # Update UI state
        self.is_running = True
        self.btn_start.configure(state="disabled"); self.btn_stop.configure(state="normal")
        self._set_led(self.led_run, True, self.P["warning"]); self.log(f"Session running on {port}")

    def refresh_ports(self):
        """Populate the combobox with detected serial ports."""
        if not SERIAL_AVAILABLE: return
        ports = serial.tools.list_ports.comports()
        values = [f"{p.device} - {p.description}" for p in ports]
        self.port_combo['values'] = values
        if values:
            self.port_combo.current(0)
        else:
            self.port_combo.set("No devices found")
            
    def get_midi_files(self):
        """Scans midi_files/ directory."""
        try:
            base_dir = get_midi_dir()
            if not base_dir.exists(): return []
            return [f.name for f in base_dir.glob("*.mid")]
        except: return []

    def refresh_midi_list(self):
        vals = self.get_midi_files()
        self.midi_combo['values'] = vals
        if vals and not self.midi_var.get():
             self.midi_combo.current(0)

    def get_existing_sessions(self):
        """
        Scans logs/ for custom session names (folders).
        Ignores default timestamped folders (start with 'session_').
        """
        try:
            log_dir = get_logs_dir()
            if not log_dir.exists(): return []
            
            # Find folders that are NOT default sessions
            # Default sessions look like "session_2025-..."
            custom_names = []
            for d in log_dir.iterdir():
                if d.is_dir():
                    # Filter out default auto-generated folders ("session_2...") 
                    # to only show custom named sessions.
                    if not d.name.startswith("session_2"): 
                        custom_names.append(d.name)

            custom_names.sort()
            return custom_names
        except Exception:
            return []

    def refresh_session_list(self):
        vals = self.get_existing_sessions()
        
        # Always use a Combobox (Writable) so user can Type NEW or Select EXISTING
        # We assume self.session_input_widget is already a Combobox (created in __init__)
        
        # Ensure it has not been swapped to an Entry by legacy code
        if not isinstance(self.session_input_widget, ttk.Combobox):
            # If for some reason it's an Entry, swap it back to Combobox permanently
            self.session_input_widget.destroy()
            self.session_input_widget = ttk.Combobox(self.session_row, textvariable=self.session_name_var)
            self.session_input_widget.pack(side="left", fill="x", expand=True, padx=(0, 5))
            
        self.session_input_widget['values'] = vals



    def refresh_analysis_subjects(self):
        """Populate the first dropdown with Subject/Folder names."""
        try:
            log_dir = get_logs_dir()
            if not log_dir.exists(): 
                self.subject_combo['values'] = []
                return

            # Get just the directories (subjects)
            subjects = [d.name for d in log_dir.iterdir() if d.is_dir()]
            subjects.sort()
            
            self.subject_combo['values'] = subjects
            if subjects:
                self.subject_combo.current(0)
                self.on_subject_selected(None) # Trigger update of second list
        except Exception as e:
            print(f"Error loading subjects: {e}")

    def on_subject_selected(self, event):
        """When a subject is picked, populate the second dropdown with sessions."""
        subject = self.subject_var.get()
        if not subject: return
        
        try:
            log_dir = get_logs_dir() / subject
            if not log_dir.exists():
                self.session_combo['values'] = []
                return

            # Find session folders
            sessions = [d.name for d in log_dir.iterdir() if d.is_dir() and d.name.startswith("session_")]
            sessions.sort(reverse=True) # Newest first
            
            self.session_combo['values'] = sessions
            if sessions:
                self.session_combo.current(0)
            else:
                self.session_var.set("No sessions")
        except Exception as e:
            print(f"Error loading sessions: {e}")
             
    def view_session_plot(self):
        subject = self.subject_var.get()
        session_name = self.session_var.get()

        if not subject or not session_name or session_name == "No sessions":
            return
        
        # Construct path from both dropdowns
        base_dir = get_logs_dir() / subject / session_name
        plot_path = base_dir / "BPM_plot.png"
        
        if not plot_path.exists():
            # If PNG missing, try generate it on demand
            csv_path = base_dir / "session_data.csv"
            if csv_path.exists():
                try:
                    from utils.plotter import generate_post_session_plot
                    print(f"DEBUG: Generating plot for {base_dir}...")
                    generate_post_session_plot(base_dir)
                except Exception as e:
                    print(f"DEBUG: Plot generation failed: {e}")
                    import traceback
                    traceback.print_exc()
        
        if not plot_path.exists():
            messagebox.showinfo("No Plot", f"No plot found for {session_name}\n(Make sure the session finished correctly)")
            return
            
        # Create Popup Window
        top = tk.Toplevel(self.root)
        top.title(f"Analysis: {subject} / {session_name}")
        top.geometry("1100x850") # Fallback size
        top.configure(bg=self.P["bg"])
        
        # Maximize window (Windows only)
        try: top.state("zoomed")
        except: pass

        # Using Label with Dynamic Resizing (Requires Pillow)
        try:
            from PIL import Image, ImageTk
            
            # Load original image
            original_image = Image.open(plot_path)
            
            # Create a label to hold the image
            lbl = ttk.Label(top, background=self.P["bg"])
            lbl.pack(fill="both", expand=True)
            
            def resize_image(event):
                # Calculate aspect ratio to fit window
                new_width = event.width
                new_height = event.height
                
                if new_width < 10 or new_height < 10: return
                
                # Resize (LANCZOS for quality)
                resized = original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized)
                
                lbl.configure(image=photo)
                lbl.image = photo # Keep reference
                
            # Bind resize event
            lbl.bind("<Configure>", resize_image)
            
        except ImportError:
            # Fallback to standard scrollbars if PIL not available (though it should be)
            print("DEBUG: PIL not found, falling back to scrollbars")
            container = ttk.Frame(top)
            container.pack(fill="both", expand=True)
            canvas = tk.Canvas(container, bg=self.P["bg"], highlightthickness=0, bd=0)
            hbar = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview,
                               style="Horizontal.TScrollbar")
            vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview,
                               style="Vertical.TScrollbar")
            scrollable_frame = ttk.Frame(canvas, style="TFrame")
            scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            vbar.pack(side="right", fill="y")
            hbar.pack(side="bottom", fill="x")
            
            try:
                img = tk.PhotoImage(file=str(plot_path))
                l = ttk.Label(scrollable_frame, image=img, background=self.P["bg"])
                l.image = img
                l.pack()
            except Exception as e:
                ttk.Label(scrollable_frame, text=f"Error: {e}").pack()




    def stop_session(self):
        """Action for the 'STOP SESSION' button."""
        if self.session_thread: self.session_thread.stop()
        self.is_running = False
        self.btn_start.configure(state="normal"); self.btn_stop.configure(state="disabled")
        self._set_led(self.led_run, False); self.log("Stopped")
        
        # VISUAL: Connect dots on stop
        try:
            if self.live_data_buffer:
                import pandas as pd
                df = pd.DataFrame(self.live_data_buffer)
                
                # Preprocess DF (match logic in refresh_plot)
                df.rename(columns={"t": "time", "s": "song_bpm", "w": "walking_bpm", "e": "step_event"}, inplace=True)
                if "time" in df.columns:
                     df["seconds"] = df["time"].apply(_elapsed_to_seconds)
                else:
                     df["seconds"] = df.index
                     
                self.plotter.finalize_plot(df)
                self.canvas.draw()
        except Exception as e:
            print(f"Final plot update failed: {e}")

        # Generate Post-Session Plot
        if self.current_session_dir:
            try:
                self.log("Generating plot...")
                generate_post_session_plot(self.current_session_dir)
                self.log(f"Saved plot to {self.current_session_dir.name}")
            except Exception as e:
                self.log(f"Plot failed: {e}")

        # Reset live buffers and plot for next session
        # self.live_data_buffer = [] # Retain buffer so user can see last session
        # if self.plotter:
        #    self.plotter.reset()
        #    self._did_tight_layout = False
        try:
            self.canvas.draw_idle()
        except Exception:
            pass



    def apply_smoothing_up(self):
        try:
            val = self.smoothing_up_var.get().strip()
            # If default/empty, use 0.02
            if not val or val == "Set Climbing": 
                v = 0.02
            else:
                v = float(val)
            if self.session_thread: self.session_thread.update_smoothing_alpha_up(v)
            self.log(f"Climbing set to {v}")
        except:
            self.log("Invalid Climbing value")

    def apply_smoothing_down(self):
        try:
            val = self.smoothing_down_var.get().strip()
            # If default/empty, use 0.05
            if not val or val == "Set Cascading":
                v = 0.05
            else:
                v = float(val)
            if self.session_thread: self.session_thread.update_smoothing_alpha_down(v)
            self.log(f"Cascading set to {v}")
        except:
            self.log("Invalid Cascading value")
            
    def apply_esp_config(self, type_key, var):
        """Sends new config to the running session thread."""
        if not self.session_thread or not self.is_running:
            self.log("Session not running - Setting saved for start")
            return

        try:
            val = var.get().strip()
            # Fallback for empty or placeholder text
            if not val or val.startswith("Set "):
                 v = 10 if type_key == "window" else 1
            else:
                 v = int(val)
                 
            self.session_thread.update_esp_config(type_key, v)
            self.log(f"{type_key.title()} set to {v}")
        except:
            self.log(f"Invalid {type_key} value")

    def on_calibrate_weight(self):
        """Run calibration without requiring a session; blocks start until done."""
        if self.is_calibrating:
            self.log("Calibration already in progress.")
            return
        if send_calibration_command is None:
            self.log("Calibration helper unavailable.")
            return

        # Derive port (strip description if needed)
        port_val = self.port_var.get().strip()
        if not port_val:
            self.log("Select a serial port first.")
            return
        # If combobox value is like "COM3 - desc", take first token
        port = port_val.split()[0]

        try:
            margin = int(self.cal_margin_var.get())
        except ValueError:
            margin = 200
            self.log("Invalid margin; using 200.")

        # UI lockout during calibration
        self.is_calibrating = True
        self._cal_spinner_idx = 0
        self.btn_calibrate.configure(state="disabled")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        self._animate_calibration_spinner()

        def _worker():
            ok = False
            try:
                import serial
                with serial.Serial(port, 115200, timeout=1.0) as ser:
                    class _Logger:
                        def log(self, msg): self_outer.log(msg)
                    ok = send_calibration_command(ser, _Logger(), margin=margin, retries=3)
            except Exception as e:
                self.log(f"Calibration failed: {e}")
            finally:
                self.root.after(0, lambda ok=ok: self._finish_calibration(ok))

        self_outer = self
        threading.Thread(target=_worker, daemon=True).start()

    def _animate_calibration_spinner(self):
        """Animate spinner in calibration button while calibrating."""
        if not self.is_calibrating:
            return
        frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        self.btn_calibrate.configure(text=f"Calibrating {frames[self._cal_spinner_idx % len(frames)]}")
        self._cal_spinner_idx += 1
        self.root.after(100, self._animate_calibration_spinner)

    def _finish_calibration(self, success: bool):
        """Reset UI after calibration with brief result flash."""
        self.is_calibrating = False
        # Show result briefly
        if success:
            self.btn_calibrate.configure(text="✓ Done!", state="disabled")
            self.log("Calibration completed.")
        else:
            self.btn_calibrate.configure(text="✗ Failed", state="disabled")
        # Restore button after delay
        self.root.after(1500, self._restore_calibration_button)

    def _restore_calibration_button(self):
        """Restore calibration button to normal state."""
        self.btn_calibrate.configure(state="normal", text="✅ CALIBRATE WEIGHT")
        # Re-enable start; stop remains as-is depending on running state
        if not self.is_running:
            self.btn_start.configure(state="normal")
        else:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")

    # ====================== TRAINING TAB ======================
    def _build_training_tab(self, parent):
        """Build the Model Training tab UI."""
        self.is_training = False
        self.training_process = None

        # Use PanedWindow for resizable two-column layout
        paned = ttk.PanedWindow(parent, orient="horizontal", style="TPanedwindow")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # ---- LEFT: Session Selection ----
        left_card = ttk.Frame(paned, style="Card.TFrame", padding=15)
        paned.add(left_card, weight=1)

        ttk.Label(left_card, text="Select Sessions for Training", style="CardHeader.TLabel").pack(anchor="w")
        ttk.Label(left_card, text="Check users/sessions to include in training data",
                  style="CardSub.TLabel").pack(anchor="w", pady=(0, 10))

        # Treeview for session selection
        tree_frame = ttk.Frame(left_card, style="TFrame")
        tree_frame.pack(fill="both", expand=True, padx=0, pady=0)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", style="Vertical.TScrollbar")
        self.session_tree = ttk.Treeview(tree_frame, columns=("sessions",), show="tree",
                                          selectmode="extended", yscrollcommand=tree_scroll.set,
                                          style="Treeview")
        tree_scroll.configure(command=self.session_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.session_tree.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        self.session_tree.column("#0", width=300, stretch=True)
        self.session_tree.heading("#0", text="User / Session")

        # Buttons under tree
        tree_btn_frame = ttk.Frame(left_card, style="Card.TFrame")
        tree_btn_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(tree_btn_frame, text="↻ Refresh", command=self._refresh_training_sessions,
                   style="Compact.TButton").pack(side="left", padx=(0, 5))
        ttk.Button(tree_btn_frame, text="Select All", command=self._select_all_sessions,
                   style="Compact.TButton").pack(side="left", padx=(0, 5))
        ttk.Button(tree_btn_frame, text="🔄 Generate Augmented Data", command=self._generate_augmented_data,
                   style="Compact.TButton").pack(side="left", padx=(0, 5))
        ttk.Button(tree_btn_frame, text="🗑️ Delete Selected", command=self._delete_selected_sessions,
                   style="Compact.TButton").pack(side="left")
        
        # Augmentation progress
        self.augmentation_progress = ttk.Progressbar(left_card, mode="indeterminate", length=200)
        self.augmentation_progress.pack(fill="x", pady=(10, 5))
        
        self.augmentation_status_var = tk.StringVar(value="")
        self.augmentation_status_label = ttk.Label(left_card, textvariable=self.augmentation_status_var, 
                                                    style="CardSub.TLabel", font=("Segoe UI", 9))
        self.augmentation_status_label.pack(anchor="w")
        
        # Hide progress bar initially
        self.augmentation_progress.pack_forget()
        self.augmentation_status_label.pack_forget()

        # ---- RIGHT: Training Options & Controls ----
        right_card = ttk.Frame(paned, style="Card.TFrame", padding=15)
        paned.add(right_card, weight=1)

        ttk.Label(right_card, text="Training Options", style="CardHeader.TLabel").pack(anchor="w")

        # Algorithm selection
        algo_frame = ttk.Frame(right_card, style="Card.TFrame")
        algo_frame.pack(fill="x", pady=(10, 5))
        ttk.Label(algo_frame, text="Algorithm:", style="CardLabel.TLabel").pack(side="left")
        self.algo_var = tk.StringVar(value="LightGBM")
        algo_combo = ttk.Combobox(algo_frame, textvariable=self.algo_var, state="readonly", width=15)
        algo_combo['values'] = ["LightGBM"]  # Expandable later
        algo_combo.pack(side="left", padx=(10, 0))

        # Training type selection
        type_frame = ttk.Frame(right_card, style="Card.TFrame")
        type_frame.pack(fill="x", pady=5)
        ttk.Label(type_frame, text="Training Type:", style="CardLabel.TLabel").pack(side="left")
        self.train_type_var = tk.StringVar(value="base")
        ttk.Radiobutton(type_frame, text="Base Model", variable=self.train_type_var, value="base").pack(side="left", padx=(10, 5))
        ttk.Radiobutton(type_frame, text="User Head", variable=self.train_type_var, value="user_head").pack(side="left")

        # User head options (shown when user_head selected)
        self.user_head_frame = ttk.Frame(right_card, style="Card.TFrame")
        self.user_head_frame.pack(fill="x", pady=5)
        ttk.Label(self.user_head_frame, text="User Name:", style="CardLabel.TLabel").pack(side="left")
        self.user_head_name_var = tk.StringVar(value="")
        ttk.Entry(self.user_head_frame, textvariable=self.user_head_name_var, width=20).pack(side="left", padx=(10, 0))
        ttk.Label(self.user_head_frame, text="(for saving head artifact)", style="CardSub.TLabel").pack(side="left", padx=(5, 0))

        # Optuna optimization checkbox (only for base model)
        optuna_frame = ttk.Frame(right_card, style="Card.TFrame")
        optuna_frame.pack(fill="x", pady=5)
        self.optuna_var = tk.BooleanVar(value=False)
        self.optuna_check = ttk.Checkbutton(optuna_frame, text="Optuna Hyperparameter Optimization",
                                             variable=self.optuna_var, command=self._on_optuna_change)
        self.optuna_check.pack(side="left")
        
        # Optuna trials setting
        self.optuna_trials_frame = ttk.Frame(right_card, style="Card.TFrame")
        ttk.Label(self.optuna_trials_frame, text="Trials:", style="CardLabel.TLabel").pack(side="left")
        self.optuna_trials_var = tk.StringVar(value="30")
        ttk.Entry(self.optuna_trials_frame, textvariable=self.optuna_trials_var, width=6).pack(side="left", padx=(5, 0))
        ttk.Label(self.optuna_trials_frame, text="(more = better but slower)", style="CardSub.TLabel").pack(side="left", padx=(5, 0))

        # Bind radio button change (must be after optuna widgets are created)
        self.train_type_var.trace_add("write", lambda *_: self._on_train_type_change())
        self._on_train_type_change()  # Initial state

        # Separator
        ttk.Separator(right_card, orient="horizontal").pack(fill="x", pady=15)

        # Progress section
        ttk.Label(right_card, text="Training Progress", style="CardHeader.TLabel").pack(anchor="w")

        self.train_progress = ttk.Progressbar(right_card, mode="indeterminate", length=300)
        self.train_progress.pack(fill="x", pady=(10, 5))

        self.train_status_var = tk.StringVar(value="Ready to train")
        ttk.Label(right_card, textvariable=self.train_status_var, style="CardSub.TLabel").pack(anchor="w")

        # Training log (small text area)
        log_frame = ttk.Frame(right_card, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.train_log = tk.Text(log_frame, height=8, wrap="word", font=("Consolas", 9),
                                  bg=self.P["bg"], fg=self.P["text_main"], insertbackground=self.P["text_main"],
                                  relief="flat", borderwidth=0, highlightthickness=0)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.train_log.yview, 
                                   style="Vertical.TScrollbar")
        self.train_log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.train_log.pack(side="left", fill="both", expand=True)
        self.train_log.configure(state="disabled")

        # Buttons row
        btn_row = ttk.Frame(right_card, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(15, 0))

        self.btn_train = ttk.Button(btn_row, text="🚀 START TRAINING", command=self._start_training,
                                     style="Primary.TButton")
        self.btn_train.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_view_results = ttk.Button(btn_row, text="📊 VIEW RESULTS", command=self._view_training_results,
                                            style="Secondary.TButton")
        self.btn_view_results.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Populate sessions on init
        self.root.after(100, self._refresh_training_sessions)

    def _on_train_type_change(self):
        """Show/hide user head options based on selection."""
        # Guard: optuna widgets may not exist yet during init
        has_optuna = hasattr(self, "optuna_check")
        
        if self.train_type_var.get() == "user_head":
            self.user_head_frame.pack(fill="x", pady=5)
            if has_optuna:
                self.optuna_check.configure(state="disabled")
                self.optuna_var.set(False)
                self.optuna_trials_frame.pack_forget()
        else:
            self.user_head_frame.pack_forget()
            if has_optuna:
                self.optuna_check.configure(state="normal")

    def _on_optuna_change(self):
        """Show/hide Optuna trials setting based on checkbox."""
        if self.optuna_var.get():
            self.optuna_trials_frame.pack(fill="x", pady=5)
        else:
            self.optuna_trials_frame.pack_forget()

    def _refresh_training_sessions(self):
        """Scan logs directory and populate session tree."""
        self.session_tree.delete(*self.session_tree.get_children())
        logs_dir = get_logs_dir()
        if not logs_dir.exists():
            return

        for user_dir in sorted(logs_dir.iterdir()):
            if not user_dir.is_dir():
                continue
            
            # Handle Augmented folder (nested structure: Augmented/UserName/session_*)
            if user_dir.name == "Augmented":
                aug_node = self.session_tree.insert("", "end", text=f"📁 {user_dir.name}", open=False, tags=("user",))
                # Iterate through user folders inside Augmented
                for aug_user_dir in sorted(user_dir.iterdir()):
                    if not aug_user_dir.is_dir():
                        continue
                    aug_user_node = self.session_tree.insert(aug_node, "end", text=f"📁 {aug_user_dir.name}", open=False, tags=("user",))
                    sessions = sorted(aug_user_dir.glob("session_*/session_data.csv"))
                    for sess in sessions:
                        sess_name = sess.parent.name
                        self.session_tree.insert(aug_user_node, "end", text=f"  📄 {sess_name}",
                                                  values=(str(sess),), tags=("session",))
            else:
                # Regular user folder (Default, Eitan, etc.)
                user_node = self.session_tree.insert("", "end", text=f"📁 {user_dir.name}", open=False, tags=("user",))
                sessions = sorted(user_dir.glob("session_*/session_data.csv"))
                for sess in sessions:
                    sess_name = sess.parent.name
                    self.session_tree.insert(user_node, "end", text=f"  📄 {sess_name}",
                                              values=(str(sess),), tags=("session",))

    def _select_all_sessions(self):
        """Select all items in session tree."""
        def select_recursive(item):
            self.session_tree.selection_add(item)
            for child in self.session_tree.get_children(item):
                select_recursive(child)
        for item in self.session_tree.get_children():
            select_recursive(item)

    def _generate_augmented_data(self):
        """Generate augmented data from selected sessions."""
        import threading
        import subprocess
        import sys
        from pathlib import Path
        
        # Get selected items
        selected = self.session_tree.selection()
        if not selected:
            self.log("Select sessions or user folders to augment.")
            return
        
        # Parse selection to determine mode
        selected_users = []
        selected_sessions = []
        
        for item in selected:
            tags = self.session_tree.item(item, "tags")
            item_text = self.session_tree.item(item, "text")
            
            if "session" in tags:
                # Individual session selected
                vals = self.session_tree.item(item, "values")
                if vals:
                    selected_sessions.append(vals[0])
            elif "user" in tags:
                # User folder selected
                # Extract user name from "📁 UserName"
                user_name = item_text.replace("📁", "").strip()
                if user_name != "Augmented":  # Don't augment the Augmented folder itself
                    selected_users.append(user_name)
        
        # Build command
        base_dir = Path(__file__).resolve().parent.parent
        script_path = base_dir / "research" / "LightGBM" / "generate_augmented_data.py"
        
        if not script_path.exists():
            self.log(f"ERROR: Augmentation script not found at {script_path}")
            return
        
        # Determine command based on selection
        if selected_users and not selected_sessions:
            # User folder(s) selected - augment first user only for simplicity
            # (Could be extended to support multiple users)
            mode = f"user folder '{selected_users[0]}'"
            cmd = [sys.executable, str(script_path), "--user", selected_users[0]]
        elif selected_sessions:
            # Specific sessions selected
            mode = f"{len(selected_sessions)} specific session(s)"
            cmd = [sys.executable, str(script_path), "--sessions"] + selected_sessions
        else:
            self.log("Select sessions or user folders to augment.")
            return
        
        self.log(f"Generating augmented data for {mode}...")
        self.log("This may take a few minutes...")
        
        # Show progress bar and update status
        self.augmentation_progress.pack(fill="x", pady=(10, 5))
        self.augmentation_status_label.pack(anchor="w")
        self.augmentation_progress.start(10)
        self.augmentation_status_var.set("🔄 Generating augmented data...")
        
        # Run in background thread
        def _worker():
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(base_dir),
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )
                
                # Update GUI from main thread
                def _update_gui():
                    # Stop and hide progress bar
                    self.augmentation_progress.stop()
                    self.augmentation_progress.pack_forget()
                    
                    if result.returncode == 0:
                        self.log("✓ Augmentation complete!")
                        self.augmentation_status_var.set("✓ Augmentation complete!")
                        # Show output
                        for line in result.stdout.strip().split('\n'):
                            if line.strip():
                                self.log(f"  {line}")
                        # Refresh session tree to show new augmented sessions
                        self._refresh_training_sessions()
                        # Hide status after 3 seconds
                        self.root.after(3000, lambda: self.augmentation_status_label.pack_forget())
                    else:
                        self.log(f"✗ Augmentation failed with code {result.returncode}")
                        self.augmentation_status_var.set("✗ Augmentation failed")
                        if result.stderr:
                            self.log(f"Error: {result.stderr}")
                        # Hide status after 5 seconds
                        self.root.after(5000, lambda: self.augmentation_status_label.pack_forget())
                
                self.root.after(0, _update_gui)
            
            except subprocess.TimeoutExpired:
                def _timeout_gui():
                    self.augmentation_progress.stop()
                    self.augmentation_progress.pack_forget()
                    self.augmentation_status_var.set("✗ Augmentation timed out")
                    self.log("✗ Augmentation timed out (>10 minutes)")
                    self.root.after(5000, lambda: self.augmentation_status_label.pack_forget())
                self.root.after(0, _timeout_gui)
            except Exception as e:
                def _error_gui():
                    self.augmentation_progress.stop()
                    self.augmentation_progress.pack_forget()
                    self.augmentation_status_var.set(f"✗ Error: {e}")
                    self.log(f"✗ Augmentation error: {e}")
                    self.root.after(5000, lambda: self.augmentation_status_label.pack_forget())
                self.root.after(0, _error_gui)
        
        threading.Thread(target=_worker, daemon=True).start()

    def _delete_selected_sessions(self):
        """Delete selected sessions or folders from disk and refresh UI."""
        from tkinter import messagebox
        import shutil
        from pathlib import Path
        
        # Get selected items
        selected = self.session_tree.selection()
        if not selected:
            self.log("Select sessions or user folders to delete.")
            return
        
        # Parse selection to get paths to delete
        items_to_delete = []
        user_folders_to_delete = []
        
        for item in selected:
            tags = self.session_tree.item(item, "tags")
            item_text = self.session_tree.item(item, "text")
            
            if "session" in tags:
                # Individual session selected
                vals = self.session_tree.item(item, "values")
                if vals:
                    csv_path = Path(vals[0])
                    session_dir = csv_path.parent
                    items_to_delete.append(("session", session_dir))
            elif "user" in tags:
                # User folder selected - delete entire folder
                user_name = item_text.replace("📁", "").strip()
                user_folder = get_logs_dir() / user_name
                if user_folder.exists():
                    items_to_delete.append(("folder", user_folder))
                    user_folders_to_delete.append(user_name)
        
        if not items_to_delete:
            self.log("No sessions or folders found to delete.")
            return
        
        # Count items for confirmation message
        session_count = sum(1 for item_type, _ in items_to_delete if item_type == "session")
        folder_count = sum(1 for item_type, _ in items_to_delete if item_type == "folder")
        
        # Build confirmation message
        msg_parts = []
        if folder_count > 0:
            folder_word = "folder" if folder_count == 1 else "folders"
            msg_parts.append(f"{folder_count} entire {folder_word}")
        if session_count > 0:
            session_word = "session" if session_count == 1 else "sessions"
            msg_parts.append(f"{session_count} {session_word}")
        
        items_text = " and ".join(msg_parts)
        
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {items_text}?\n\n"
            f"This action cannot be undone!\n\n"
            f"Deleted items will be removed from:\n"
            f"  • Model Training tab\n"
            f"  • Analysis tab\n"
            f"  • File system (permanently)",
            icon="warning"
        )
        
        if not confirm:
            self.log("Deletion cancelled.")
            return
        
        # Delete items
        deleted_count = 0
        failed_count = 0
        
        for item_type, path in items_to_delete:
            try:
                shutil.rmtree(path)
                deleted_count += 1
                if item_type == "folder":
                    self.log(f"✓ Deleted entire folder: {path.name}")
                else:
                    self.log(f"✓ Deleted: {path.name}")
            except Exception as e:
                failed_count += 1
                self.log(f"✗ Failed to delete {path.name}: {e}")
        
        # Summary
        if deleted_count > 0:
            self.log(f"✓ Successfully deleted {deleted_count} item(s)")
        if failed_count > 0:
            self.log(f"✗ Failed to delete {failed_count} item(s)")
        
        # Refresh both training and analysis tabs
        self._refresh_training_sessions()
        self.refresh_analysis_subjects()

    def _get_selected_session_paths(self):
        """Get list of selected session CSV paths."""
        paths = []
        for item in self.session_tree.selection():
            tags = self.session_tree.item(item, "tags")
            if "session" in tags:
                vals = self.session_tree.item(item, "values")
                if vals:
                    paths.append(vals[0])
            elif "user" in tags:
                # If user folder selected, include all its sessions
                for child in self.session_tree.get_children(item):
                    vals = self.session_tree.item(child, "values")
                    if vals:
                        paths.append(vals[0])
        return list(set(paths))  # Dedupe

    def _log_training(self, msg):
        """Append message to training log."""
        self.train_log.configure(state="normal")
        self.train_log.insert("end", msg + "\n")
        self.train_log.see("end")
        self.train_log.configure(state="disabled")

    def _start_training(self):
        """Start model training as background subprocess."""
        print("[DEBUG] _start_training called")
        if self.is_training:
            self.log("Training already in progress.")
            return
        if self.is_running:
            self.log("Cannot train while a session is running.")
            return

        selected = self._get_selected_session_paths()
        print(f"[DEBUG] Selected {len(selected)} sessions")
        if not selected:
            self.log("Select at least one session to train on.")
            return

        train_type = self.train_type_var.get()
        user_head_name = self.user_head_name_var.get().strip()
        print(f"[DEBUG] train_type={train_type}, user_head_name='{user_head_name}'")
        use_optuna = self.optuna_var.get() and train_type == "base"
        try:
            optuna_trials = int(self.optuna_trials_var.get())
        except ValueError:
            optuna_trials = 30

        if train_type == "user_head" and not user_head_name:
            self.log("Enter a user name for the head artifact.")
            print("[DEBUG] Missing user name for user_head training")
            return
        
        print("[DEBUG] Starting training worker thread...")

        # Lock UI
        self.is_training = True
        self.btn_train.configure(state="disabled", text="Training...")
        self.btn_start.configure(state="disabled")
        self.train_progress.start(10)
        self.train_status_var.set("Training in progress...")
        self.train_log.configure(state="normal")
        self.train_log.delete("1.0", "end")
        self.train_log.configure(state="disabled")

        mode = f"{train_type} + Optuna ({optuna_trials} trials)" if use_optuna else train_type
        self._log_training(f"Starting {mode} training with {len(selected)} session(s)...")

        # Run training in background thread
        def _worker():
            import subprocess
            import sys
            try:
                # Write sessions to a temp file to avoid command-line length limits on Windows
                import tempfile
                sessions_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                for s in selected:
                    sessions_file.write(s + '\n')
                sessions_file.close()
                
                if train_type == "base":
                    # Run train_lgbm.py with selected sessions
                    script = get_research_dir() / "LightGBM" / "train_lgbm.py"
                    cmd = [sys.executable, str(script), "--sessions-file", sessions_file.name]
                    # Add Optuna optimization if enabled
                    if use_optuna:
                        cmd.append("--optimize")
                        cmd.extend(["--trials", str(optuna_trials)])
                else:
                    # Run train_user_head.py with selected sessions
                    script = get_research_dir() / "LightGBM" / "train_user_head.py"
                    cmd = [sys.executable, str(script), "--sessions-file", sessions_file.name, "--suffix", user_head_name.replace(" ", "_")]

                self.root.after(0, lambda: self._log_training(f"Running: {' '.join(cmd)}"))

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=str(get_app_root())
                )
                self.training_process = proc

                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self.root.after(0, lambda l=line: self._log_training(l))

                proc.wait()
                success = proc.returncode == 0
                self.root.after(0, lambda: self._finish_training(success))

            except Exception as e:
                self.root.after(0, lambda: self._log_training(f"Error: {e}"))
                self.root.after(0, lambda: self._finish_training(False))
            finally:
                # Cleanup temp sessions file
                try:
                    import os
                    if 'sessions_file' in dir() and sessions_file and os.path.exists(sessions_file.name):
                        os.unlink(sessions_file.name)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_training(self, success: bool):
        """Reset UI after training completes."""
        self.is_training = False
        self.training_process = None
        self.train_progress.stop()

        if success:
            self.train_status_var.set("✓ Training completed successfully!")
            self._log_training("Training finished successfully.")
            self.btn_train.configure(text="✓ Done!")
        else:
            self.train_status_var.set("✗ Training failed")
            self._log_training("Training failed. Check log above.")
            self.btn_train.configure(text="✗ Failed")

        # Restore button after delay
        self.root.after(2000, self._restore_train_button)

    def _restore_train_button(self):
        """Restore train button to normal state."""
        self.btn_train.configure(state="normal", text="🚀 START TRAINING")
        if not self.is_running:
            self.btn_start.configure(state="normal")

    def _view_training_results(self):
        """Open a window displaying training result plots."""
        results_dir = get_plots_dir()
        
        if not results_dir.exists():
            messagebox.showinfo("No Results", "No training results found. Run training first.")
            return
        
        # Find available plots
        plots = list(results_dir.glob("*.png"))
        if not plots:
            messagebox.showinfo("No Results", "No plot images found in results directory.")
            return
        
        # Create results window
        results_win = tk.Toplevel(self.root)
        results_win.title("Training Results")
        results_win.geometry("1200x900")
        results_win.configure(bg=self.P["bg"])
        
        # Header
        header = ttk.Frame(results_win, style="TFrame")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Label(header, text="📊 Model Training Results", style="H1.TLabel").pack(anchor="w")
        ttk.Label(header, text=f"Found {len(plots)} result plot(s)", style="Sub.TLabel").pack(anchor="w")
        
        # Plot selector
        selector_frame = ttk.Frame(results_win, style="TFrame")
        selector_frame.pack(fill="x", padx=20, pady=(0, 10))
        ttk.Label(selector_frame, text="Select Plot:", style="Sub.TLabel").pack(side="left")
        
        plot_names = [p.stem for p in sorted(plots)]
        plot_var = tk.StringVar(value=plot_names[0] if plot_names else "")
        plot_combo = ttk.Combobox(selector_frame, textvariable=plot_var, values=plot_names, state="readonly", width=40)
        plot_combo.pack(side="left", padx=(10, 0))
        
        # Image display area - minimal padding to maximize image space
        img_frame = ttk.Frame(results_win, style="Card.TFrame", padding=5)
        img_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        img_label = ttk.Label(img_frame, text="Select a plot to view", style="CardLabel.TLabel", anchor="center")
        img_label.pack(fill="both", expand=True)
        
        # Store reference to prevent garbage collection
        results_win._photo_ref = None
        results_win._current_plot_path = None
        
        def load_plot(*_):
            selected = plot_var.get()
            if not selected:
                return
            plot_path = results_dir / f"{selected}.png"
            if not plot_path.exists():
                return
            
            # Store current plot path for resize events
            results_win._current_plot_path = plot_path
            
            try:
                # Use the shared loading function
                load_plot_from_path(plot_path)
            except ImportError:
                img_label.configure(text=f"PIL/Pillow not installed.\nPlot saved at:\n{plot_path}", image="")
        
        plot_combo.bind("<<ComboboxSelected>>", load_plot)
        
        # Reload plot on window resize with debouncing to prevent flickering
        results_win._resize_timer = None
        def on_resize(event=None):
            # Only reload if we have a plot loaded and event is from the main window
            if event and event.widget != results_win:
                return
            if results_win._current_plot_path is not None:
                # Cancel previous timer if exists
                if results_win._resize_timer:
                    results_win.after_cancel(results_win._resize_timer)
                # Schedule reload after 200ms of no resize events
                results_win._resize_timer = results_win.after(200, lambda: load_plot_from_path(results_win._current_plot_path))
        
        def load_plot_from_path(plot_path):
            """Helper to reload plot from a specific path."""
            try:
                from PIL import Image, ImageTk
                img = Image.open(plot_path)
                
                # Force window to update geometry before measuring
                results_win.update_idletasks()
                
                # Get actual window size
                win_width = results_win.winfo_width()
                win_height = results_win.winfo_height()
                
                # Use window dimensions with minimal margins (header ~80px, padding ~40px)
                max_w = max(400, win_width - 50)
                max_h = max(300, win_height - 130)
                
                # Scale to fit available space while maintaining aspect ratio
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_label.configure(image=photo, text="")
                results_win._photo_ref = photo
            except Exception as e:
                img_label.configure(text=f"Error loading image: {e}", image="")
        
        results_win.bind("<Configure>", on_resize)
        
        # Open folder button
        def open_folder():
            import os
            os.startfile(str(results_dir)) if os.name == 'nt' else os.system(f'open "{results_dir}"')
        
        ttk.Button(selector_frame, text="📁 Open Folder", command=open_folder, style="Compact.TButton").pack(side="right")
        
        # Load first plot
        if plot_names:
            results_win.after(100, load_plot)

    # ====================== ANALYSIS TAB ======================
    def _build_analysis_tab(self, parent):
        """Build the Analysis tab UI for viewing past sessions."""
        # Main container
        container = ttk.Frame(parent, style="TFrame")
        container.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Title
        ttk.Label(container, text="📊  Session Analysis", style="H1.TLabel", 
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Label(container, text="Review and analyze past training sessions", 
                 style="Sub.TLabel").pack(anchor="w", pady=(0, 20))
        
        # Selection card
        select_card = ttk.Frame(container, style="Card.TFrame", padding=20)
        select_card.pack(fill="x", pady=(0, 15))
        
        ttk.Label(select_card, text="SELECT SESSION", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Subject selection
        ttk.Label(select_card, text="Subject / User", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        subject_row = ttk.Frame(select_card, style="Card.TFrame")
        subject_row.pack(fill="x", pady=(0, 15))
        
        self.subject_combo = ttk.Combobox(subject_row, textvariable=self.subject_var, 
                                          state="readonly", height=15, font=("Segoe UI", 11), width=40)
        self.subject_combo.pack(side="left", padx=(0, 10))
        self.subject_combo.bind("<<ComboboxSelected>>", self.on_subject_selected)
        ttk.Button(subject_row, text="🔄 Refresh", style="Compact.TButton", 
                  command=self.refresh_analysis_subjects).pack(side="left")
        
        # Session selection
        ttk.Label(select_card, text="Session", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        session_row = ttk.Frame(select_card, style="Card.TFrame")
        session_row.pack(fill="x")
        
        self.session_combo = ttk.Combobox(session_row, textvariable=self.session_var, 
                                          state="readonly", height=15, font=("Segoe UI", 11), width=40)
        self.session_combo.pack(side="left", padx=(0, 10))
        self.session_combo.bind("<<ComboboxSelected>>", self.load_analysis_plot)
        ttk.Button(session_row, text="📊 Load Plot", style="CompactPrimary.TButton", 
                  command=self.load_analysis_plot).pack(side="left")
        
        # Plot display card
        self.analysis_plot_card = ttk.Frame(container, style="Card.TFrame", padding=20)
        self.analysis_plot_card.pack(fill="both", expand=True)
        
        # Header with zoom controls
        plot_header = ttk.Frame(self.analysis_plot_card, style="Card.TFrame")
        plot_header.pack(fill="x", pady=(0, 15))
        
        ttk.Label(plot_header, text="SESSION PLOT", style="CardHeader.TLabel").pack(side="left")
        
        # Zoom controls
        zoom_frame = ttk.Frame(plot_header, style="Card.TFrame")
        zoom_frame.pack(side="right")
        
        ttk.Button(zoom_frame, text="🔍−", style="Compact.TButton", width=4, 
                  command=self.zoom_out_analysis).pack(side="left", padx=2)
        
        self.zoom_level_var = tk.StringVar(value="100%")
        ttk.Label(zoom_frame, textvariable=self.zoom_level_var, style="CardLabel.TLabel", 
                 font=("Segoe UI", 9, "bold"), width=6).pack(side="left", padx=5)
        
        ttk.Button(zoom_frame, text="🔍+", style="Compact.TButton", width=4, 
                  command=self.zoom_in_analysis).pack(side="left", padx=2)
        
        ttk.Button(zoom_frame, text="⊡", style="Compact.TButton", width=4, 
                  command=self.zoom_fit_analysis).pack(side="left", padx=(8, 0))
        
        # Scrollable plot area
        plot_scroll_frame = ttk.Frame(self.analysis_plot_card, style="Card.TFrame")
        plot_scroll_frame.pack(fill="both", expand=True)
        
        # Canvas with scrollbars for zoom
        self.analysis_plot_canvas = tk.Canvas(plot_scroll_frame, bg=self.P["card_bg"], highlightthickness=0, bd=0)
        h_scroll = ttk.Scrollbar(plot_scroll_frame, orient="horizontal", command=self.analysis_plot_canvas.xview,
                                style="Horizontal.TScrollbar")
        v_scroll = ttk.Scrollbar(plot_scroll_frame, orient="vertical", command=self.analysis_plot_canvas.yview,
                                style="Vertical.TScrollbar")
        
        self.analysis_plot_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.analysis_plot_canvas.pack(side="left", fill="both", expand=True)
        
        # Plot label inside canvas (will be updated with image)
        self.analysis_plot_label = ttk.Label(self.analysis_plot_canvas, text="Select a session to view its plot", 
                 style="CardSub.TLabel", anchor="center")
        self.analysis_plot_window = self.analysis_plot_canvas.create_window(0, 0, window=self.analysis_plot_label, 
                                                                            anchor="nw")
        
        # Store reference to prevent garbage collection and track zoom
        self.analysis_photo_ref = None
        self.analysis_original_image = None
        self.analysis_zoom_level = 1.0
        
        # Bind canvas resize to update plot display
        self.analysis_plot_canvas.bind("<Configure>", lambda e: self._on_analysis_canvas_resize())
        
        # Mouse wheel scrolling for zoomed plot
        def on_analysis_mousewheel(event):
            if self.analysis_zoom_level > 1.0:
                # Calculate scroll amount (10% of view per scroll)
                scroll_amount = 0.1 * (-1 if event.delta > 0 else 1)
                
                # Shift+scroll for horizontal, regular scroll for vertical
                if event.state & 0x1:  # Shift key held
                    x_pos = self.analysis_plot_canvas.xview()[0] + scroll_amount
                    self.analysis_plot_canvas.xview_moveto(max(0, min(1, x_pos)))
                else:
                    y_pos = self.analysis_plot_canvas.yview()[0] + scroll_amount
                    self.analysis_plot_canvas.yview_moveto(max(0, min(1, y_pos)))
        
        self.analysis_plot_canvas.bind("<MouseWheel>", on_analysis_mousewheel)
        
        # Also bind keyboard arrows for panning when zoomed
        def on_analysis_key(event):
            if self.analysis_zoom_level > 1.0:
                scroll_amount = 0.05  # 5% per key press
                if event.keysym == "Left":
                    x_pos = self.analysis_plot_canvas.xview()[0] - scroll_amount
                    self.analysis_plot_canvas.xview_moveto(max(0, min(1, x_pos)))
                elif event.keysym == "Right":
                    x_pos = self.analysis_plot_canvas.xview()[0] + scroll_amount
                    self.analysis_plot_canvas.xview_moveto(max(0, min(1, x_pos)))
                elif event.keysym == "Up":
                    y_pos = self.analysis_plot_canvas.yview()[0] - scroll_amount
                    self.analysis_plot_canvas.yview_moveto(max(0, min(1, y_pos)))
                elif event.keysym == "Down":
                    y_pos = self.analysis_plot_canvas.yview()[0] + scroll_amount
                    self.analysis_plot_canvas.yview_moveto(max(0, min(1, y_pos)))
        
        self.analysis_plot_canvas.bind("<Left>", on_analysis_key)
        self.analysis_plot_canvas.bind("<Right>", on_analysis_key)
        self.analysis_plot_canvas.bind("<Up>", on_analysis_key)
        self.analysis_plot_canvas.bind("<Down>", on_analysis_key)
        
        # Drag-to-pan functionality when zoomed
        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        
        def on_drag_start(event):
            if self.analysis_zoom_level > 1.0:
                self._drag_data["x"] = event.x
                self._drag_data["y"] = event.y
                self._drag_data["dragging"] = True
                self.analysis_plot_canvas.config(cursor="fleur")
                self.analysis_plot_canvas.focus_set()
        
        def on_drag_motion(event):
            if self._drag_data["dragging"] and self.analysis_zoom_level > 1.0:
                # Calculate scroll amount as fraction of canvas size
                canvas_width = self.analysis_plot_canvas.winfo_width()
                canvas_height = self.analysis_plot_canvas.winfo_height()
                
                dx = (self._drag_data["x"] - event.x) / canvas_width
                dy = (self._drag_data["y"] - event.y) / canvas_height
                
                # Get current scroll position and add delta
                x_pos = self.analysis_plot_canvas.xview()[0] + dx
                y_pos = self.analysis_plot_canvas.yview()[0] + dy
                
                # Apply scroll
                self.analysis_plot_canvas.xview_moveto(max(0, min(1, x_pos)))
                self.analysis_plot_canvas.yview_moveto(max(0, min(1, y_pos)))
                
                self._drag_data["x"] = event.x
                self._drag_data["y"] = event.y
        
        def on_drag_end(event):
            self._drag_data["dragging"] = False
            self.analysis_plot_canvas.config(cursor="")
        
        self.analysis_plot_canvas.bind("<ButtonPress-1>", on_drag_start)
        self.analysis_plot_canvas.bind("<B1-Motion>", on_drag_motion)
        self.analysis_plot_canvas.bind("<ButtonRelease-1>", on_drag_end)
        
        # Register this canvas for smart mousewheel routing
        self.scrollable_canvases.append(('analysis', self.analysis_plot_canvas, plot_scroll_frame))
        
        # Initialize data
        self.root.after(100, self.refresh_analysis_subjects)
    
    def _on_analysis_canvas_resize(self):
        """Handle canvas resize events to reflow the plot."""
        if self.analysis_original_image and hasattr(self, '_resize_timer'):
            # Cancel pending resize update
            self.root.after_cancel(self._resize_timer)
        
        if self.analysis_original_image:
            # Debounce resize events (wait 200ms after last resize)
            self._resize_timer = self.root.after(200, self._update_analysis_plot_display)
    
    def load_analysis_plot(self, event=None):
        """Load and display the selected session's plot inline."""
        subject = self.subject_var.get()
        session_name = self.session_var.get()

        if not subject or not session_name or session_name == "No sessions":
            self.analysis_plot_label.configure(text="Select a session to view its plot", image="")
            self.analysis_original_image = None
            return
        
        # Construct path from both dropdowns
        base_dir = get_logs_dir() / subject / session_name
        plot_path = base_dir / "BPM_plot.png"
        
        if not plot_path.exists():
            # If PNG missing, try generate it on demand
            csv_path = base_dir / "session_data.csv"
            if csv_path.exists():
                try:
                    from utils.plotter import generate_post_session_plot
                    generate_post_session_plot(base_dir)
                except Exception as e:
                    print(f"Plot generation failed: {e}")
        
        if not plot_path.exists():
            self.analysis_plot_label.configure(text=f"No plot found for {session_name}\n(Session may not have completed)", 
                                              image="")
            self.analysis_original_image = None
            return
            
        # Load and display the image
        try:
            from PIL import Image, ImageTk
            img = Image.open(plot_path)
            
            # Store original image for zoom operations
            self.analysis_original_image = img
            self.analysis_zoom_level = 1.0
            
            # Display at fit-to-window size initially
            self._update_analysis_plot_display()
            
        except ImportError:
            self.analysis_plot_label.configure(text=f"PIL/Pillow not installed.\nPlot saved at:\n{plot_path}", image="")
            self.analysis_original_image = None
        except Exception as e:
            self.analysis_plot_label.configure(text=f"Error loading plot: {e}", image="")
            self.analysis_original_image = None
    
    def _update_analysis_plot_display(self):
        """Update the analysis plot display with current zoom level."""
        if not self.analysis_original_image:
            return
        
        try:
            from PIL import Image, ImageTk
            
            # Get canvas dimensions
            canvas_width = self.analysis_plot_canvas.winfo_width()
            canvas_height = self.analysis_plot_canvas.winfo_height()
            
            # Use default size if canvas not yet rendered
            if canvas_width < 10:
                canvas_width = 900
            if canvas_height < 10:
                canvas_height = 450
            
            # Calculate display size based on zoom level
            img = self.analysis_original_image.copy()
            orig_w, orig_h = img.size
            
            # Calculate fit-to-window size
            fit_ratio = min(canvas_width / orig_w, canvas_height / orig_h)
            fit_ratio = min(fit_ratio, 1.0)  # Don't upscale beyond original
            
            # Apply zoom on top of fit ratio
            display_ratio = fit_ratio * self.analysis_zoom_level
            
            new_w = int(orig_w * display_ratio)
            new_h = int(orig_h * display_ratio)
            
            # Resize image
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            
            # Update label
            self.analysis_plot_label.configure(image=photo, text="")
            self.analysis_photo_ref = photo  # Keep reference
            
            # Update canvas scroll region and scroll increments
            self.analysis_plot_canvas.configure(scrollregion=(0, 0, new_w, new_h))
            
            # Set scroll increments (10% of visible area per unit)
            self.analysis_plot_canvas.configure(xscrollincrement=max(1, new_w // 20))
            self.analysis_plot_canvas.configure(yscrollincrement=max(1, new_h // 20))
            
            # Update zoom level display
            zoom_percent = int(self.analysis_zoom_level * 100)
            self.zoom_level_var.set(f"{zoom_percent}%")
            
        except Exception as e:
            print(f"Error updating plot display: {e}")
    
    def zoom_in_analysis(self):
        """Zoom in on the analysis plot."""
        if not self.analysis_original_image:
            return
        
        # Increase zoom by 25%
        self.analysis_zoom_level = min(self.analysis_zoom_level * 1.25, 5.0)  # Max 500%
        self._update_analysis_plot_display()
    
    def zoom_out_analysis(self):
        """Zoom out on the analysis plot."""
        if not self.analysis_original_image:
            return
        
        # Decrease zoom by 25%
        self.analysis_zoom_level = max(self.analysis_zoom_level / 1.25, 0.25)  # Min 25%
        self._update_analysis_plot_display()
    
    def zoom_fit_analysis(self):
        """Reset zoom to fit the analysis plot to window."""
        if not self.analysis_original_image:
            return
        
        self.analysis_zoom_level = 1.0
        self._update_analysis_plot_display()

    # ====================== MODE SETTINGS TAB ======================
    def _build_mode_settings_tab(self, parent):
        """Build the Mode Settings tab UI for configuring all modes."""
        # Main container with scrolling
        container = ttk.Frame(parent, style="TFrame")
        container.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Title
        ttk.Label(container, text="⚙  Mode Configuration", style="H1.TLabel", 
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Label(container, text="Configure advanced settings for each sync mode", 
                 style="Sub.TLabel").pack(anchor="w", pady=(0, 20))
        
        # Use PanedWindow for scrollable content
        canvas = tk.Canvas(container, bg=self.P["bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview, 
                                 style="Vertical.TScrollbar")
        scrollable_frame = ttk.Frame(canvas, style="TFrame")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", tags="inner")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Fix width
        def _configure_canvas(event):
            canvas.itemconfig("inner", width=event.width)
        canvas.bind("<Configure>", _configure_canvas)
        
        # Register this canvas for smart mousewheel routing
        self.scrollable_canvases.append(('mode_settings', canvas, scrollable_frame))
        
        # ====================== RANDOM MODE SETTINGS ======================
        random_card = ttk.Frame(scrollable_frame, style="Card.TFrame", padding=20)
        random_card.pack(fill="x", pady=(0, 15))
        
        ttk.Label(random_card, text="🎲 RANDOM MODE SETTINGS", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(random_card, text="Randomly shift the target BPM within a difficulty range", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Random Span
        ttk.Label(random_card, text="Difficulty Span", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(random_card, text="How far the target can drift from your pace (±%)", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        
        span_frame = ttk.Frame(random_card, style="Card.TFrame")
        span_frame.pack(fill="x", pady=(0, 15))
        
        # Use pre-initialized variables (already created in __init__)
        span_slider = ttk.Scale(span_frame, from_=1, to=100, orient="horizontal",
                               variable=self.random_span_display_var, command=self.on_random_slider_change)
        span_slider.pack(fill="x", padx=5)
        
        span_entry_row = ttk.Frame(random_card, style="Card.TFrame")
        span_entry_row.pack(fill="x", pady=(0, 15))
        ttk.Label(span_entry_row, text="Current:", style="CardLabel.TLabel").pack(side="left")
        span_entry = ttk.Entry(span_entry_row, textvariable=self.rnd_val_str, width=8)
        span_entry.pack(side="left", padx=(10, 5))
        span_entry.bind("<Return>", self.on_random_span_entry)
        ttk.Label(span_entry_row, text="(1 = ±1%, 100 = ±100%)", style="CardSub.TLabel").pack(side="left", padx=(10, 0))
        
        # Gamify Toggle
        ttk.Separator(random_card, orient="horizontal").pack(fill="x", pady=15)
        
        # Use pre-initialized gamify_var (already created in __init__)
        gamify_check = ttk.Checkbutton(random_card, text="Enable Gamified Mode (Time-Based Matching)", 
                                      variable=self.gamify_var, command=self.on_gamify_toggle)
        gamify_check.pack(anchor="w", pady=(0, 10))
        
        ttk.Label(random_card, text="When disabled: Simple step-counting mode\nWhen enabled: Hold target BPM for duration", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Simple Mode Settings
        ttk.Label(random_card, text="Matching Parameters", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        
        # Match Threshold
        ttk.Label(random_card, text="Match Threshold", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(random_card, text="How close your BPM needs to be to match the target", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        threshold_row = ttk.Frame(random_card, style="Card.TFrame")
        threshold_row.pack(fill="x", pady=(0, 15))
        threshold_entry = ttk.Entry(threshold_row, textvariable=self.random_simple_threshold_var, width=10, font=("Segoe UI", 10))
        threshold_entry.pack(side="left", padx=(0, 5))
        threshold_entry.bind("<Return>", self.on_random_simple_threshold_change)
        ttk.Label(threshold_row, text="BPM (1.0-20.0)", style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        
        # Match Steps/Duration (dynamic label based on gamify)
        self.lbl_match_steps_header = ttk.Label(random_card, text="Match Steps", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold"))
        self.lbl_match_steps_header.pack(anchor="w", pady=(5, 2))
        self.lbl_match_steps_desc = ttk.Label(random_card, text="Consecutive steps within threshold to hit target", 
                 style="CardSub.TLabel")
        self.lbl_match_steps_desc.pack(anchor="w", pady=(0, 5))
        steps_row = ttk.Frame(random_card, style="Card.TFrame")
        steps_row.pack(fill="x", pady=(0, 15))
        steps_entry = ttk.Entry(steps_row, textvariable=self.random_simple_steps_var, width=10, font=("Segoe UI", 10))
        steps_entry.pack(side="left", padx=(0, 5))
        steps_entry.bind("<Return>", self.on_random_simple_steps_change)
        self.lbl_match_steps_sub = ttk.Label(steps_row, text="steps (5-100)", style="CardLabel.TLabel", font=("Segoe UI", 9))
        self.lbl_match_steps_sub.pack(side="left")
        
        # Timeout
        ttk.Label(random_card, text="Timeout", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(random_card, text="Time before generating a new random target if not matched", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        timeout_row = ttk.Frame(random_card, style="Card.TFrame")
        timeout_row.pack(fill="x", pady=(0, 0))
        timeout_entry = ttk.Entry(timeout_row, textvariable=self.random_simple_timeout_var, width=10, font=("Segoe UI", 10))
        timeout_entry.pack(side="left", padx=(0, 5))
        timeout_entry.bind("<Return>", self.on_random_simple_timeout_change)
        ttk.Label(timeout_row, text="seconds (5.0-300.0)", style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        
        # ====================== HYBRID MODE SETTINGS ======================
        hybrid_card = ttk.Frame(scrollable_frame, style="Card.TFrame", padding=20)
        hybrid_card.pack(fill="x", pady=(0, 15))
        
        ttk.Label(hybrid_card, text="🚀 HYBRID MODE SETTINGS", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(hybrid_card, text="Start dynamic, lock when steady, unlock on deviation", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Lock Steps
        ttk.Label(hybrid_card, text="Lock Steps", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(hybrid_card, text="Consecutive stable steps before locking to music BPM", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        lock_row = ttk.Frame(hybrid_card, style="Card.TFrame")
        lock_row.pack(fill="x", pady=(0, 15))
        lock_entry = ttk.Entry(lock_row, textvariable=self.hybrid_lock_var, width=10, font=("Segoe UI", 10))
        lock_entry.pack(side="left", padx=(0, 5))
        lock_entry.bind("<Return>", self.on_hybrid_lock_change)
        ttk.Label(lock_row, text="steps (2-20)", style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        
        # Stability Threshold
        ttk.Label(hybrid_card, text="Stability Threshold", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(hybrid_card, text="Maximum BPM variation to consider pace stable for locking", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        stability_row = ttk.Frame(hybrid_card, style="Card.TFrame")
        stability_row.pack(fill="x", pady=(0, 15))
        stability_entry = ttk.Entry(stability_row, textvariable=self.hybrid_stability_var, width=10, font=("Segoe UI", 10))
        stability_entry.pack(side="left", padx=(0, 5))
        stability_entry.bind("<Return>", self.on_hybrid_stability_change)
        ttk.Label(stability_row, text="BPM (1.0-10.0)", style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        
        # Unlock Threshold
        ttk.Label(hybrid_card, text="Unlock Threshold", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        ttk.Label(hybrid_card, text="BPM deviation from locked tempo to trigger immediate unlock", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 5))
        unlock_thres_row = ttk.Frame(hybrid_card, style="Card.TFrame")
        unlock_thres_row.pack(fill="x", pady=(0, 0))
        unlock_thres_entry = ttk.Entry(unlock_thres_row, textvariable=self.hybrid_unlock_thres_var, width=10, font=("Segoe UI", 10))
        unlock_thres_entry.pack(side="left", padx=(0, 5))
        unlock_thres_entry.bind("<Return>", self.on_hybrid_unlock_thres_change)
        ttk.Label(unlock_thres_row, text="BPM (5.0-50.0)", style="CardLabel.TLabel", font=("Segoe UI", 9)).pack(side="left")
        
        # ====================== ADVANCED SETTINGS ======================
        advanced_card = ttk.Frame(scrollable_frame, style="Card.TFrame", padding=20)
        advanced_card.pack(fill="x", pady=(0, 15))
        
        ttk.Label(advanced_card, text="🔧 ADVANCED SETTINGS", style="CardHeader.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(advanced_card, text="Fine-tune BPM smoothing, prediction model, and sensor config", 
                 style="CardSub.TLabel").pack(anchor="w", pady=(0, 15))
        
        # Climbing (Speed Up)
        ttk.Label(advanced_card, text="Climbing (Speed Up)", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        
        attack_row = ttk.Frame(advanced_card, style="Card.TFrame")
        attack_row.pack(fill="x", pady=(0, 10))
        
        self.smoothing_up_var = tk.StringVar()
        entry_up = ttk.Entry(attack_row, textvariable=self.smoothing_up_var, width=15)
        entry_up.pack(side="left", padx=(0, 5))
        self._bind_placeholder(entry_up, self.smoothing_up_var, "Default")
        ttk.Button(attack_row, text="?", style="Help.TButton", width=2, command=self.show_attack_help).pack(side="left", padx=5)
        
        # Cascading (Slow Down)
        ttk.Label(advanced_card, text="Cascading (Slow Down)", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        
        decay_row = ttk.Frame(advanced_card, style="Card.TFrame")
        decay_row.pack(fill="x", pady=(0, 10))
        
        self.smoothing_down_var = tk.StringVar()
        entry_down = ttk.Entry(decay_row, textvariable=self.smoothing_down_var, width=15)
        entry_down.pack(side="left", padx=(0, 5))
        self._bind_placeholder(entry_down, self.smoothing_down_var, "Default")
        ttk.Button(decay_row, text="?", style="Help.TButton", width=2, command=self.show_decay_help).pack(side="left", padx=5)
        
        # Smoothing Window
        ttk.Label(advanced_card, text="Smoothing Window", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        window_row = ttk.Frame(advanced_card, style="Card.TFrame")
        window_row.pack(fill="x", pady=(0, 10))
        
        self.step_window_var = tk.StringVar()
        entry_win = ttk.Entry(window_row, textvariable=self.step_window_var, width=12)
        entry_win.pack(side="left", padx=(0, 5))
        self._bind_placeholder(entry_win, self.step_window_var, "Default")
        ttk.Label(window_row, text="Steps", style="CardLabel.TLabel").pack(side="left", padx=(0, 5))
        ttk.Button(window_row, text="?", style="Help.TButton", width=2, command=self.show_window_help).pack(side="left")
        
        # Update Stride
        ttk.Label(advanced_card, text="Update Stride", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        stride_row = ttk.Frame(advanced_card, style="Card.TFrame")
        stride_row.pack(fill="x", pady=(0, 10))
        
        self.stride_var = tk.StringVar()
        entry_stride = ttk.Entry(stride_row, textvariable=self.stride_var, width=12)
        entry_stride.pack(side="left", padx=(0, 5))
        self._bind_placeholder(entry_stride, self.stride_var, "Default")
        ttk.Label(stride_row, text="Steps", style="CardLabel.TLabel").pack(side="left", padx=(0, 5))
        ttk.Button(stride_row, text="?", style="Help.TButton", width=2, command=self.show_stride_help).pack(side="left")
        
        # Prediction Model
        ttk.Label(advanced_card, text="Prediction Model", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        model_row = ttk.Frame(advanced_card, style="Card.TFrame")
        model_row.pack(fill="x", pady=(0, 10))
        
        self.model_var = tk.StringVar(value="Base Model")
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, state="readonly", width=30)
        self.model_combo.pack(side="left", padx=(0, 5))
        ttk.Button(model_row, text="↻", style="Compact.TButton", width=3, command=self._refresh_model_list).pack(side="left")
        self._refresh_model_list()
        
        # Calibration Margin
        ttk.Label(advanced_card, text="Calibration Margin", style="CardLabel.TLabel", 
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5, 2))
        cali_frame = ttk.Frame(advanced_card, style="Card.TFrame")
        cali_frame.pack(fill="x", pady=(0, 5))
        
        self.cal_margin_var = tk.StringVar(value="200")
        ttk.Entry(cali_frame, textvariable=self.cal_margin_var, width=12).pack(side="left", padx=(0, 5))
        ttk.Label(cali_frame, text="Units", style="CardLabel.TLabel").pack(side="left")

    # ====================== THEME TOGGLE ======================
    def toggle_theme(self):
        """Toggle between light and dark mode."""
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.P = self.themes[self.theme_mode]
        
        # Update theme button icon (sun for dark mode, moon for light mode)
        theme_icon = "☀" if self.theme_mode == "dark" else "☾"
        self.theme_btn.configure(text=theme_icon)
        
        # Apply theme to root
        self.root.configure(bg=self.P["bg"])
        
        # Update canvas backgrounds  
        self.canvas_sidebar.configure(bg=self.P["card_bg"])
        self.led_canvas.configure(bg=self.P["bg"])
        
        # Update analysis plot canvas if it exists
        if hasattr(self, 'analysis_plot_canvas'):
            self.analysis_plot_canvas.configure(bg=self.P["card_bg"])
        
        # Update BPM label color
        if hasattr(self, 'bpm_val_label'):
            self.bpm_val_label.configure(foreground=self.P["text_main"], background=self.P["card_bg"])
        
        # Update all plot card backgrounds
        try:
            for widget in self.root.winfo_children():
                self._update_widget_colors(widget)
        except:
            pass
        
        # Update matplotlib figure
        self.figure.patch.set_facecolor(self.P.get("plot_bg", self.P["card_bg"]))
        
        # Update plotter theme
        if hasattr(self, 'plotter'):
            self.plotter.P = self.P
            self.plotter._style_axes(self.plotter.ax1, "LIVE BPM TRACE", "BPM", show_x=True)
        
        try:
            self.canvas.draw_idle()
        except:
            pass
        
        # Reconfigure all styles
        self._apply_theme_styles()
        
        self.log(f"Switched to {self.theme_mode.title()} Mode")

    # ====================== NOTIFICATION SYSTEM ======================
    def show_notification(self, message, duration=5000):
        """Display a temporary notification at the top-right of the session tab."""
        if not hasattr(self, 'notification_label'):
            return
        self.notification_label.configure(text=message, bg=self.P["warning"])
        self.notification_label.place(relx=0.98, rely=0.02, anchor="ne")
        
        # Auto-hide after duration
        if duration > 0:
            self.root.after(duration, self.hide_notification)

    def hide_notification(self):
        """Hide the notification."""
        if hasattr(self, 'notification_label'):
            self.notification_label.place_forget()

    def _update_widget_colors(self, widget):
        """Recursively update widget backgrounds for theme."""
        try:
            # Skip if widget doesn't exist
            if not widget.winfo_exists():
                return
                
            widget_class = widget.winfo_class()
            
            # Update Frame backgrounds
            if widget_class == "Frame" or widget_class == "TFrame":
                try:
                    # Check if it's a Card frame
                    if hasattr(widget, 'cget'):
                        try:
                            style_name = widget.cget('style')
                            if 'Card' in str(style_name):
                                widget.configure(style="Card.TFrame")
                        except:
                            pass
                except:
                    pass
            
            # Update tk.Text widgets (training log, etc.)
            elif widget_class == "Text":
                try:
                    widget.configure(bg=self.P["bg"], 
                                   fg=self.P["text_main"], 
                                   insertbackground=self.P["text_main"])
                except:
                    pass
            
            # Update tk.Canvas widgets (plots, LED canvas, etc.)
            elif widget_class == "Canvas":
                try:
                    # Check if it's a card canvas or background canvas
                    current_bg = widget.cget('bg')
                    # If it was card-colored, update to new card color
                    if current_bg in [self.themes["dark"]["card_bg"], self.themes["light"]["card_bg"]]:
                        widget.configure(bg=self.P["card_bg"])
                    else:
                        # Otherwise assume it's a main background canvas
                        widget.configure(bg=self.P["bg"])
                except:
                    pass
            
            # Recursively update children
            for child in widget.winfo_children():
                self._update_widget_colors(child)
        except:
            pass
    
    def _apply_theme_styles(self):
        """Reapply all ttk styles with current theme."""
        style = ttk.Style()
        
        # Reapply all the styles with current theme colors
        style.configure(".", background=self.P["bg"], foreground=self.P["text_main"])
        style.configure("TFrame", background=self.P["bg"], relief="flat", borderwidth=0, highlightthickness=0)
        # Card styling based on theme
        if self.theme_mode == "light":
            style.configure("Card.TFrame", background=self.P["card_bg"], relief="flat", borderwidth=0, highlightthickness=0)
        else:
            style.configure("Card.TFrame", background=self.P["card_bg"], relief="flat", borderwidth=0, highlightthickness=0)
        style.configure("H1.TLabel", foreground=self.P["text_main"], background=self.P["bg"])
        style.configure("CardHeader.TLabel", foreground=self.P["accent"], background=self.P["card_bg"])
        style.configure("Sub.TLabel", foreground=self.P["text_sub"], background=self.P["bg"])
        style.configure("CardLabel.TLabel", background=self.P["card_bg"], foreground=self.P["text_main"])
        style.configure("NavStatus.TLabel", background=self.P["bg"], foreground=self.P["accent"])
        style.configure("CardSub.TLabel", foreground=self.P["text_sub"], background=self.P["card_bg"])
        
        # Button styles
        style.configure("Primary.TButton", background=self.P["accent"], foreground="white")
        style.map("Primary.TButton", background=[("active", self.P["accent_hover"])])
        style.configure("Danger.TButton", background=self.P["danger"], foreground="white")
        style.configure("Success.TButton", background=self.P["success"], foreground="white")
        style.configure("Info.TButton", background="#3b82f6", foreground="white")
        style.map("Info.TButton", background=[("active", "#2563eb")])
        secondary_bg = "#64748b" if self.theme_mode == "light" else "#475569"
        style.configure("Secondary.TButton", background=secondary_bg, foreground="white")
        style.map("Secondary.TButton", background=[("active", "#475569" if self.theme_mode == "light" else "#334155")])
        compact_bg = "#f1f5f9" if self.theme_mode == "light" else self.P["input_bg"]
        style.configure("Compact.TButton", background=compact_bg, foreground=self.P["text_input"])
        style.map("Compact.TButton", background=[("active", "#e2e8f0" if self.theme_mode == "light" else "#f3f4f6")])
        style.configure("CompactPrimary.TButton", background=self.P["accent"], foreground="white")
        style.configure("Help.TButton", background=self.P["card_bg"], foreground=self.P["accent"])
        
        # Theme button
        style.configure("Theme.TButton", background=self.P["bg"], foreground=self.P["text_main"])
        style.map("Theme.TButton", background=[("active", self.P["highlight"])], 
                 foreground=[("active", self.P["accent"])])
        
        # Input styles - no borders/outlines, darker background
        style.configure("TEntry", 
                       fieldbackground=self.P["input_bg"], 
                       foreground=self.P["text_input"], 
                       borderwidth=0, 
                       relief="flat", 
                       highlightthickness=0,
                       insertcolor=self.P["text_input"],
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"],
                       focuscolor="")
        style.map("TEntry",
                 fieldbackground=[("focus", self.P["input_bg"])],
                 bordercolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 lightcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 darkcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])])
        style.configure("TCombobox", 
                       fieldbackground=self.P["input_bg"], 
                       foreground=self.P["text_input"],
                       background=self.P["card_bg"], 
                       borderwidth=0, 
                       relief="flat", 
                       highlightthickness=0,
                       selectbackground=self.P["accent"],
                       selectforeground="white",
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"],
                       focuscolor="",
                       insertwidth=0)
        style.map("TCombobox", 
                 fieldbackground=[("readonly", self.P["input_bg"])], 
                 foreground=[("readonly", self.P["text_input"])],
                 background=[("readonly", self.P["card_bg"])],
                 bordercolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 lightcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])],
                 darkcolor=[("focus", self.P["card_bg"]), ("!focus", self.P["card_bg"])])
        style.configure("TRadiobutton", background=self.P["card_bg"], foreground=self.P["text_main"],
                       borderwidth=0, relief="flat", highlightthickness=0)
        style.configure("TCheckbutton", background=self.P["bg"], foreground=self.P["text_main"],
                       borderwidth=0, relief="flat", highlightthickness=0)
        
        # Other components - borderless
        style.configure("TPanedwindow", background=self.P["bg"], borderwidth=0, relief="flat")
        style.configure("TSeparator", background=self.P["border"])
        style.configure("Treeview", background=self.P["card_bg"], foreground=self.P["text_main"], 
                       fieldbackground=self.P["card_bg"], borderwidth=0,
                       relief="flat", highlightthickness=0,
                       bordercolor=self.P["card_bg"],
                       lightcolor=self.P["card_bg"],
                       darkcolor=self.P["card_bg"])
        style.configure("Treeview.Heading",
                       background=self.P["card_bg"],
                       foreground=self.P["text_main"],
                       borderwidth=0,
                       relief="flat")
        style.map("Treeview", background=[("selected", self.P["accent"])], foreground=[("selected", "white")])
        style.configure("TNotebook", 
                       background=self.P["bg"], 
                       borderwidth=0, 
                       relief="flat", 
                       highlightthickness=0,
                       bordercolor=self.P["bg"],
                       lightcolor=self.P["bg"],
                       darkcolor=self.P["bg"],
                       tabmargins=[0, 0, 0, 0])
        # Remove ALL border elements from the notebook
        style.layout("TNotebook", [
            ("Notebook.client", {"sticky": "nswe", "border": 0})
        ])
        style.layout("TNotebook.Tab", [
            ("Notebook.tab", {
                "sticky": "nswe",
                "children": [
                    ("Notebook.padding", {
                        "side": "top",
                        "sticky": "nswe",
                        "children": [
                            ("Notebook.label", {"side": "top", "sticky": ""})
                        ]
                    })
                ]
            })
        ])
        tab_bg = self.P["card_bg"] if self.theme_mode == "light" else self.P["border"]
        style.configure("TNotebook.Tab", background=tab_bg, foreground=self.P["text_sub"], 
                       borderwidth=0, relief="flat",
                       focuscolor="",
                       lightcolor=self.P["bg"],
                       darkcolor=self.P["bg"],
                       bordercolor=self.P["bg"])
        style.map("TNotebook.Tab", 
                 background=[("selected", self.P["accent"])], 
                 foreground=[("selected", "white")],
                 lightcolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])],
                 darkcolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])],
                 bordercolor=[("selected", self.P["bg"]), ("!selected", self.P["bg"])])
        style.configure("TScale", background=self.P["card_bg"], troughcolor=self.P["border"])
        style.configure("TProgressbar", troughcolor=self.P["border"], background=self.P["accent"])
        
        # Scrollbar - blend with background
        style.configure("Vertical.TScrollbar",
                       background=self.P["card_bg"],
                       troughcolor=self.P["card_bg"],
                       borderwidth=0,
                       arrowsize=0,
                       relief="flat")
        style.configure("Horizontal.TScrollbar",
                       background=self.P["card_bg"],
                       troughcolor=self.P["card_bg"],
                       borderwidth=0,
                       arrowsize=0,
                       relief="flat")

    def show_attack_help(self):
        msg = ("Controls how fast the music SPEEDS UP when you accelerate.\n\n"
               "Low (0.05) = Gradual climbing.\n"
               "Default (0.1) = Balanced response.\n"
               "High (0.20) = Snappy response.\n"
               "Note: 'Sprint Boost' will override this if you run very fast.")
        messagebox.showinfo("Climbing Smoothing", msg)

    def show_decay_help(self):
        msg = ("Controls how fast the music SLOWS DOWN when you stop walking.\n\n"
               "Low (0.01) = Very slow, cinematic cascading.\n"
               "High (0.20) = Fast, responsive drop.\n\n"
                "Recommended: 0.02")
        messagebox.showinfo("Cascading Smoothing", msg)
        
    def show_window_help(self):
        msg = ("Controls how many steps are averaged to calculate your BPM.\n\n"
               "Low (1-3): Very responsive, but jumpy.\n"
               "High (10-20): Very stable, but reacts slowly.\n\n"
               "Recommended: 3-6")
        messagebox.showinfo("Step Averaging", msg)

    def show_stride_help(self):
        msg = ("Controls how often the music BPM is updated.\n\n"
               "1 = Update every step (Smoothest).\n"
               "2 = Update every 2 steps.\n"
               "4 = Update every 4 steps (Less CPU load).\n\n"
               "Recommended: 1")
        messagebox.showinfo("Update Stride", msg)

    def quit_app(self):
        """Cleanly exit the application."""
        self.is_app_active = False
        
        # Cancel all pending poll tasks to avoid "invalid command name" errors
        if self.job_status: self.root.after_cancel(self.job_status)
        if self.job_dir: self.root.after_cancel(self.job_dir)
        if self.job_plot: self.root.after_cancel(self.job_plot)
        if self.job_ports: self.root.after_cancel(self.job_ports)

        if self.session_thread: self.session_thread.stop()
        self.root.quit()
        self.root.destroy()

    # --- POLLING LOOPS ---
    # Tkinter isn't thread-safe, so we check Queues for messages from the background thread.
    
    def enqueue_status(self, m): self.status_queue.put(m)
    def enqueue_session_dir(self, p):
        self.session_dir_queue.put(p)
    def enqueue_data(self, d):
        self.data_queue.put(d)
    
    def poll_status(self):
        """Checks for new status messages every 200ms."""
        if not self.is_app_active: return

        while not self.status_queue.empty():
            msg = self.status_queue.get_nowait()
            # Check for notification command
            if msg.startswith("NOTIFICATION:"):
                notification_text = msg.split(":", 1)[1]
                # Add emojis for visual feedback
                if "System ready" in notification_text or "Music started" in notification_text:
                    notification_text = "✅ " + notification_text
                elif "begin walking" in notification_text.lower() or "Collecting" in notification_text:
                    notification_text = "⚠️ " + notification_text
                self.show_notification(notification_text, duration=5000)
            else:
                self.log(msg)  # Regular log message
        self.job_status = self.root.after(200, self.poll_status)
        
    def poll_session_dir(self):
        """Checks if a new session folder was created."""
        if not self.is_app_active: return
        while not self.session_dir_queue.empty():
            self.current_session_dir = self.session_dir_queue.get_nowait()
            self.log(f"Logging: {self.current_session_dir.name}")
        self.job_dir = self.root.after(500, self.poll_session_dir)
        
    def poll_plot(self):
        """Updates the graph every 50ms (20 FPS)."""
        if not self.is_app_active: return
        
        if self.current_session_dir: self.refresh_plot()
        
        self.job_plot = self.root.after(50, self.poll_plot)

    def poll_ports(self):
        """Checks for new serial ports every 2 seconds (THREADED)."""
        if not SERIAL_AVAILABLE: return
        
        # Avoid overlapping scans
        if self.port_scan_thread and self.port_scan_thread.is_alive():
            self.job_ports = self.root.after(2000, self.poll_ports)
            return

        self.port_scan_thread = threading.Thread(target=self._scan_ports_background, daemon=True)
        self.port_scan_thread.start()
        self.job_ports = self.root.after(2000, self.poll_ports)

    def _scan_ports_background(self):
        try:
            ports = serial.tools.list_ports.comports()
            self.root.after(0, lambda: self._update_ports_ui(ports))
        except: pass

    def _update_ports_ui(self, ports):
        try:
            current_selection = self.port_var.get()
            new_values = [f"{p.device} - {p.description}" for p in ports]
            
            # Update only if changed to avoid UI flicker
            if list(self.port_combo['values']) != new_values:
                self.port_combo['values'] = new_values
                
                if not new_values:
                    self.port_combo.set("No devices found")
                elif current_selection not in new_values:
                    # Current selected device disappeared, or first run
                    if "No devices" in current_selection or current_selection == "":
                         self.port_combo.current(0)
                    else:
                        self.port_combo.current(0)
        except: pass

    def refresh_plot(self):
        """
        Reads from RAM Buffer (Fast!) instead of Disk CSV.
        """
        stage = "drain"
        df = None

        new_data_count = 0
        try:
            # 1. Drain Queue into RAM Buffer
            while not self.data_queue.empty():
                self.live_data_buffer.append(self.data_queue.get_nowait())
                new_data_count += 1
            
            # Hard cap to prevent unbounded growth
            stage = "cap"
            if len(self.live_data_buffer) > self.buffer_cap:
                self.live_data_buffer = self.live_data_buffer[-self.buffer_cap:]
                
            if not self.live_data_buffer or new_data_count == 0:
                return

            # 2. Convert to DataFrame (OPTIMIZED: Only process the tail!)
            stage = "dataframe"
            points_to_process = self.live_data_buffer[-8000:]
            df = pd.DataFrame(points_to_process)
            
            # Rename match plotter expectations
            # Packet keys: t=time_str, s=song, w=walking, e=event
            df.rename(columns={"t": "time", "s": "song_bpm", "w": "walking_bpm", "e": "step_event"}, inplace=True)
            
            if "time" in df.columns:
                 df["seconds"] = df["time"].apply(_elapsed_to_seconds)
            else:
                 df["seconds"] = df.index

            # Ensure time ordering for plotting (engine can emit out-of-order timestamps)
            try:
                df = df.sort_values("seconds", kind="mergesort").reset_index(drop=True)
            except Exception:
                pass

            # Ensure boolean
            if "step_event" in df.columns:
                 # It comes as boolean from JSON, but just in case
                 df["step_event"] = df["step_event"].astype(bool)

            # Early exit if conversion failed
            if df.empty:
                return

            # Sliding window after 100 seconds to prevent performance issues
            stage = "window"
            tmax = df["seconds"].max()
            if pd.isna(tmax):
                return
            
            # After 100 seconds, start sliding window to keep performance stable
            window_size = 100  # seconds
            if tmax > window_size:
                window_start = tmax - window_size
                keep_mask = df["seconds"] >= window_start
                if not keep_mask.all():
                    df = df[keep_mask].reset_index(drop=True)
                    
                # Also trim the live_data_buffer to prevent memory growth
                if len(self.live_data_buffer) > 10000:
                    self.live_data_buffer = self.live_data_buffer[-8000:]
                
            # Downsample for rendering only (keep full buffer for history/export)
            stage = "downsample"
            if len(df) > self.max_live_points:
                step = max(1, len(df) // self.max_live_points)
                df_full = df
                df = df.iloc[::step].reset_index(drop=True)
                # Guarantee we keep the latest point for axis limits
                if not df.empty and not df_full.empty:
                    if df.iloc[-1]["seconds"] != df_full.iloc[-1]["seconds"]:
                        df = pd.concat([df, df_full.iloc[[-1]]], ignore_index=True)
            
            # Delegate to Plotter
            stage = "plotter_update"
            self.plotter.update(df)
            
            stage = "layout"
            if not self._did_tight_layout:
                try:
                    self.figure.tight_layout()
                    self._did_tight_layout = True
                except: 
                    pass
            
            stage = "draw"
            try:
                self.canvas.draw_idle()
            except Exception:
                pass

        except Exception as e:
            print(f"Plot Error ({stage}): {e}")
            return
        finally:
            pass

    def update_plot_options(self):
        """Callback for the 2x/0.5x BPM checkboxes."""
        self.plotter.set_show_multipliers(self.show_2x_var.get(), self.show_half_var.get())
        # Force immediate refresh of current view if data exists
        if self.live_data_buffer:
            self.refresh_plot()

    @staticmethod
    def _parse_bpm(v):
        try: return float(v) if float(v) >= 0 else None
        except: return None

    def _bind_placeholder(self, entry, text_var, placeholder):
        """Adds placeholder text to an entry."""
        def on_focus_in(event):
            if text_var.get() == placeholder:
                text_var.set("")
                entry.configure(foreground=self.P["text_input"])
        def on_focus_out(event):
            if not text_var.get():
                text_var.set(placeholder)
                entry.configure(foreground="#94a3b8")
        if not text_var.get() or text_var.get() == placeholder:
            text_var.set(placeholder)
            entry.configure(foreground="#94a3b8")
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

def main():
    root = tk.Tk()
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    GuiApp(root)
    root.mainloop()

if __name__ == "__main__": main()
