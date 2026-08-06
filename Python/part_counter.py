import tkinter as tk
from tkinter import font, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk

# --- 1. Hardware & System Configuration (Cross-Platform) ---
try:
    import RPi.GPIO as GPIO
    ON_PI = True
    print("Raspberry Pi detected. Hardware relays ENABLED.")
    
    RELAY_PIN = 17
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    GPIO.output(RELAY_PIN, GPIO.LOW)
except (ImportError, RuntimeError):
    ON_PI = False
    print("Windows/PC detected. Hardware relays DISABLED. Running in UI Test Mode.")

# Vision Configuration
LINE_Y = 195      
OFFSET = 15       

# Global State
counter = 0
already_counted = False
system_running = False

# --- 2. Main Window Setup (Modern Dark Theme) ---
root = tk.Tk()
root.title("Visual Part Counter - Dashboard")
root.geometry("800x480") 
root.configure(bg="#1E1E2D") # Very dark, modern background

# Custom Fonts
header_font = font.Font(family="Helvetica", size=16, weight="bold")
title_font = font.Font(family="Helvetica", size=12, weight="bold")
value_font = font.Font(family="Helvetica", size=32, weight="bold")
small_font = font.Font(family="Helvetica", size=10, weight="bold")

# --- 3. UI Layout (Card Design) ---

# Top Header Card
header_frame = tk.Frame(root, bg="#27293D", height=50)
header_frame.pack(fill=tk.X, side=tk.TOP)
tk.Label(header_frame, text="PART COUNTING VISUAL MONITOR", bg="#27293D", fg="#FFFFFF", font=header_font).pack(pady=10)

# Left Column (Camera & Calibration)
left_column = tk.Frame(root, bg="#1E1E2D")
left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15, pady=15)

# Camera & Calibration Card
cam_card = tk.Frame(left_column, bg="#27293D", bd=0, relief="flat")
cam_card.pack(fill=tk.BOTH, expand=True)

tk.Label(cam_card, text="LIVE FEED & CALIBRATION", bg="#27293D", fg="#9A9A9A", font=title_font).pack(anchor="w", padx=15, pady=(10, 0))

# Video Display
video_label = tk.Label(cam_card, bg="#000000")
video_label.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

# Sliders Section
slider_frame = tk.Frame(cam_card, bg="#27293D")
slider_frame.pack(fill=tk.X, padx=15, pady=(0, 10))

# Lighting Threshold Slider (UPDATED UI)
thresh_frame = tk.Frame(slider_frame, bg="#27293D")
thresh_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
tk.Label(thresh_frame, text="Lighting Threshold:", bg="#27293D", fg="#9A9A9A", font=small_font).pack(anchor="w")
thresh_slider = tk.Scale(thresh_frame, from_=0, to_=255, orient=tk.HORIZONTAL, 
                         bg="#27293D", fg="#00F2FE", highlightthickness=0, bd=0, 
                         troughcolor="#1E1E2D", sliderrelief="raised", 
                         sliderlength=22, width=14, activebackground="#00D2D3")
thresh_slider.set(100)
thresh_slider.pack(fill=tk.X)

# Min Area Slider (UPDATED UI)
area_frame = tk.Frame(slider_frame, bg="#27293D")
area_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
tk.Label(area_frame, text="Min Part Size (Area):", bg="#27293D", fg="#9A9A9A", font=small_font).pack(anchor="w")
area_slider = tk.Scale(area_frame, from_=50, to_=5000, orient=tk.HORIZONTAL, 
                       bg="#27293D", fg="#00F2FE", highlightthickness=0, bd=0, 
                       troughcolor="#1E1E2D", sliderrelief="raised", 
                       sliderlength=22, width=14, activebackground="#00D2D3")
area_slider.set(500)
area_slider.pack(fill=tk.X)


# Right Column (Data & Controls)
right_column = tk.Frame(root, bg="#1E1E2D", width=280)
right_column.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 15), pady=15)
right_column.pack_propagate(False) # Keep width strict

# Stat Card 1: The Circular Progress
progress_card = tk.Frame(right_column, bg="#27293D", bd=0)
progress_card.pack(fill=tk.X, pady=(0, 10))

tk.Label(progress_card, text="BATCH PROGRESS", bg="#27293D", fg="#9A9A9A", font=title_font).pack(anchor="w", padx=15, pady=(10, 0))

# Custom Tkinter Canvas for Round Progress Bar
canvas_size = 140
progress_canvas = tk.Canvas(progress_card, width=canvas_size, height=canvas_size, bg="#27293D", highlightthickness=0)
progress_canvas.pack(pady=5)

def draw_circular_progress(percentage):
    progress_canvas.delete("all")
    x0, y0, x1, y1 = 10, 10, canvas_size-10, canvas_size-10
    progress_canvas.create_arc(x0, y0, x1, y1, start=0, extent=359, outline="#344648", style=tk.ARC, width=12)
    
    extent = -(percentage / 100) * 359
    if extent == 0: extent = -0.1 
    progress_canvas.create_arc(x0, y0, x1, y1, start=90, extent=extent, outline="#00F2FE", style=tk.ARC, width=12)
    
    progress_canvas.create_text(canvas_size/2, canvas_size/2, text=f"{int(percentage)}%", fill="white", font=value_font)

draw_circular_progress(0)

# Stat Card 2: Current & Target Values
data_card = tk.Frame(right_column, bg="#27293D", bd=0)
data_card.pack(fill=tk.X, pady=(0, 10))

left_data = tk.Frame(data_card, bg="#27293D")
left_data.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, pady=10)
right_data = tk.Frame(data_card, bg="#27293D")
right_data.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH, pady=10)

tk.Label(left_data, text="COUNTED", bg="#27293D", fg="#9A9A9A", font=small_font).pack()
val_current = tk.Label(left_data, text="0", bg="#27293D", fg="#00F2FE", font=value_font)
val_current.pack()

tk.Label(right_data, text="TARGET", bg="#27293D", fg="#9A9A9A", font=small_font).pack()
val_set = tk.Entry(right_data, bg="#1E1E2D", fg="white", font=font.Font(family="Helvetica", size=20, weight="bold"), justify="center", insertbackground="white", width=5, relief="flat")
val_set.insert(0, "500")
val_set.pack(pady=5)

# Control Card (Buttons)
control_card = tk.Frame(right_column, bg="#27293D", bd=0)
control_card.pack(fill=tk.BOTH, expand=True)

status_lbl = tk.Label(control_card, text="SYSTEM STOPPED", bg="#FF5252", fg="white", font=title_font, pady=5)
status_lbl.pack(fill=tk.X, padx=10, pady=(10, 15))

btn_frame = tk.Frame(control_card, bg="#27293D")
btn_frame.pack(fill=tk.X, padx=10)

# --- 4. Logic Functions ---
def update_progress_ui():
    try:
        target = int(val_set.get())
        if target > 0:
            pct = (counter / target) * 100
            if pct > 100: pct = 100
            draw_circular_progress(pct)
            val_current.config(text=str(counter))
    except ValueError:
        pass

def start_system():
    global system_running
    try:
        target = int(val_set.get())
        if target <= 0: raise ValueError
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid Target Value.")
        return
        
    system_running = True
    status_lbl.config(text="RUNNING", bg="#00D2D3") 
    if ON_PI: GPIO.output(RELAY_PIN, GPIO.HIGH)

def stop_system():
    global system_running
    system_running = False
    status_lbl.config(text="SYSTEM STOPPED", bg="#FF5252") 
    if ON_PI: GPIO.output(RELAY_PIN, GPIO.LOW)

def reset_count():
    global counter
    stop_system()
    counter = 0
    update_progress_ui()

# Buttons
btn_start = tk.Button(btn_frame, text="START", bg="#00D2D3", fg="white", font=title_font, relief="flat", command=start_system, height=2)
btn_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

btn_stop = tk.Button(btn_frame, text="STOP", bg="#FF5252", fg="white", font=title_font, relief="flat", command=stop_system, height=2)
btn_stop.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(5, 0))

btn_reset = tk.Button(control_card, text="Reset Counter", bg="#344648", fg="white", font=small_font, relief="flat", command=reset_count)
btn_reset.pack(pady=15)

# --- 5. Camera & Vision Logic ---
cap = cv2.VideoCapture(0)

def update_camera_feed():
    global counter, already_counted, system_running
    
    ret, frame = cap.read()
    if ret:
        frame = cv2.resize(frame, (450, 260))
        
        current_thresh = thresh_slider.get()
        current_min_area = area_slider.get()
        
        if system_running:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, current_thresh, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            line_color = (0, 255, 0)
            part_in_zone = False
            
            for cnt in contours:
                if cv2.contourArea(cnt) < current_min_area:
                    continue
                    
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    
                    cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
                    
                    if (cy > LINE_Y - OFFSET) and (cy < LINE_Y + OFFSET):
                        part_in_zone = True
                        if not already_counted:
                            counter += 1
                            update_progress_ui()
                            already_counted = True
                            line_color = (0, 0, 255)
                            
                            if counter >= int(val_set.get()):
                                stop_system()
                                
            if not part_in_zone:
                already_counted = False
                
            cv2.line(frame, (0, LINE_Y), (450, LINE_Y), line_color, 2)
            
        cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        img = Image.fromarray(cv2image)
        imgtk = ImageTk.PhotoImage(image=img)
        
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)
        
    root.after(15, update_camera_feed)

# --- 6. Start Application ---
def on_closing():
    stop_system()
    if ON_PI: GPIO.cleanup()
    cap.release()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
update_camera_feed()
root.mainloop()