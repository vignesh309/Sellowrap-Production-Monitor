# Import necessary modules
import os
import json
import time
import threading
import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any, List

import cv2  # type: ignore
from PIL import Image, ImageTk
from skimage.metrics import structural_similarity as ssim  # type: ignore
import subprocess
import cups  # type: ignore
import sys

# Global variables required by the script
global_camera: Any = None
camera_lock = threading.Lock()
ZOOM_FACTOR = 1  # 1.0 = no zoom, >1.0 = zoom in
ng_sample_count = 0 

# GPIO Setup handling for Windows (Testing) vs Raspberry Pi (Production)
if sys.platform.startswith('win'):
    class FakeGPIO:
        BCM = 11
        BOARD = 10
        OUT = 1
        IN = 0
        HIGH = 1
        LOW = 0
        PUD_UP = 2
        def setmode(self, mode: int) -> None: pass
        def setup(self, channel: int, direction: int, **kwargs: Any) -> None: pass
        def output(self, channel: int, value: Any) -> None: pass
        def input(self, channel: int) -> int: return 1  # Assume button not pressed
        def cleanup(self) -> None: pass
    GPIO = FakeGPIO()
else:
    import RPi.GPIO as GPIO  # type: ignore
    GPIO.setmode(GPIO.BCM)

# GPIO Pin Definitions
BUTTON_PIN = 22
BUTTON_PIN1 = 5
OK_PIN = 27
NG_PIN = 17

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_PIN1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(OK_PIN, GPIO.OUT)
GPIO.setup(NG_PIN, GPIO.OUT)

# Set initial state
GPIO.output(OK_PIN, GPIO.LOW)
GPIO.output(NG_PIN, GPIO.LOW)


# --- Camera & Utilities ---
def init_camera():
    global global_camera
    if global_camera is None or not getattr(global_camera, "isOpened", lambda: False)():
        camera = cv2.VideoCapture(0)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1600)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1200)

        start = time.time()
        while not getattr(camera, "isOpened", lambda: False)():
            if time.time() - start > 5:
                raise Exception("Camera failed to open within timeout.")
            time.sleep(0.2)
        global_camera = camera

def send_tspl_command_to_printer(printer_name, tspl_command):
    try:
        with open("/dev/usb/lp0", "wb") as printer:
            printer.write(tspl_command.encode("utf-8"))
        return True, "TSPL command sent to USB printer."
    except Exception as e:
        return False, f"USB printing error: {e}"

def apply_zoom(frame, zoom_factor):
    if zoom_factor <= 1.0:
        return frame
    h, w = frame.shape[:2]
    center_x, center_y = w // 2, h // 2
    new_w, new_h = int(w / zoom_factor), int(h / zoom_factor)
    x1 = max(center_x - new_w // 2, 0)
    y1 = max(center_y - new_h // 2, 0)
    x2 = min(center_x + new_w // 2, w)
    y2 = min(center_y + new_h // 2, h)
    cropped = frame[y1:y2, x1:x2]
    return cv2.resize(cropped, (w, h))

def capture_frame_to_file(path, zoom_factor=1):
    global global_camera
    with camera_lock:
        print("[INFO] Initializing camera for capture...")
        init_camera()
        
        if global_camera is None:
            return False, None

        for _ in range(10):  # Warm up camera
            global_camera.read()
            time.sleep(0.1)

        ret, frame = global_camera.read()
        if not ret or frame is None:
            print("[ERROR] Camera frame capture failed.")
            return False, None

        frame = apply_zoom(frame, zoom_factor)
        cv2.imwrite(path, frame)
        print(f"[INFO] Frame captured and saved to {path}")
        return True, frame

def capture_frame(zoom_factor=1):
    global global_camera
    with camera_lock:
        print("[INFO] Initializing camera for capture...")
        init_camera()

        if global_camera is None:
            return False, None

        for _ in range(10):  # Warm up camera
            global_camera.read()
            time.sleep(0.1)

        ret, frame = global_camera.read()
        if not ret or frame is None:
            print("[ERROR] Camera frame capture failed.")
            return False, None

        frame = apply_zoom(frame, zoom_factor)
        print("[INFO] Frame captured successfully.")
        return True, frame

def get_paths(part):
    part_id = part.lower().replace(" ", "_")
    return {
        "reference": f"reference_{part_id}.jpg",
        "roi": f"rois_{part_id}.json"
    }


# ------------------------ InspectorPage ------------------------
class InspectorPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller
        self._image_refs: List[Any] = []  # Prevents garbage collection cleanly

        left_frame = tk.Frame(self, bg="#1e1e1e")
        right_frame = tk.Frame(self, bg="#2c2c2c", width=300)
        left_frame.pack(side="left", fill="both", expand=True)
        right_frame.pack(side="right", fill="y")

        self.image_label = tk.Label(left_frame, bg="black")
        self.image_label.pack(fill="both", expand=True, padx=10, pady=10)

        self.part_label = tk.Label(right_frame, text="", font=("Arial", 14), bg="#2c2c2c", fg="white")
        self.part_label.pack(pady=(20, 10))

        self.overall_status = tk.Label(right_frame, text="Not Started", font=("Arial", 48), fg="white", bg="#2c2c2c")
        self.overall_status.pack(pady=(10, 20))

        self.roi_status_frame = tk.Frame(right_frame, bg="#1e1e1e", bd=2, relief="sunken")
        self.roi_status_frame.pack(pady=10, fill="both", expand=True)

        self.start_button = tk.Button(right_frame, text="Start Inspection",
                                      command=lambda: threading.Thread(target=self.run_inspection, daemon=True).start(),
                                      height=2, width=20, bg="#444444", fg="white")
        self.start_button.pack(pady=10)

        self.back_button = tk.Button(right_frame, text="Back",
                                     command=self.logout, height=2, width=20,
                                     bg="#444444", fg="white")
        self.back_button.pack(pady=(0, 20))

        # Start GPIO Button Monitoring
        self.running = True
        self.gpio_thread = threading.Thread(target=self.monitor_button, daemon=True)
        self.gpio_thread.start()

    def logout(self):
        global ng_sample_count
        ng_sample_count = 0
        self.controller.show_frame(LoginPage)

    def refresh(self):
        self._image_refs.clear()
        self.part_label.config(text="")
        self.image_label.config(image="")
        self.overall_status.config(text="Status: Not Started", fg="white")

        for widget in self.roi_status_frame.winfo_children():
            widget.destroy()

    def identify_part(self, captured_image, reference_dir=".", threshold=0.50):
        captured_gray = cv2.cvtColor(captured_image, cv2.COLOR_BGR2GRAY)
        best_score = 0
        best_part = None

        print("[INFO] Identifying part...")

        for file in os.listdir(reference_dir):
            if file.startswith("reference_") and file.endswith(".jpg"):
                part_name = file[len("reference_"):-4].replace("_", " ")
                ref_img = cv2.imread(os.path.join(reference_dir, file))
                if ref_img is None:
                    continue
                ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)

                h, w = ref_gray.shape
                captured_resized = cv2.resize(captured_gray, (w, h))

                try:
                    score = ssim(ref_gray, captured_resized)
                except Exception as e:
                    print(f"[ERROR] SSIM failed for {part_name}: {e}")
                    score = 0

                if score > best_score:
                    best_score = score
                    best_part = part_name

        print(f"[RESULT] Best match: {best_part} (Score: {best_score:.2f})")
        return best_part if best_score >= threshold else None

    def monitor_button(self):
        while self.running:
            try:
                if GPIO.input(BUTTON_PIN) == GPIO.LOW:
                    time.sleep(0.05)
                    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
                        self.controller.after(0, lambda: threading.Thread(target=self.run_inspection, daemon=True).start())
                        while GPIO.input(BUTTON_PIN) == GPIO.LOW and self.running:
                            time.sleep(0.1)
                time.sleep(0.1)
            except Exception as e:
                print("GPIO Monitoring Error:", e)

    def run_inspection(self):
        print("[INFO] run_inspection triggered.")
        self.controller.after(0, self.refresh)

        part_data = getattr(self.controller, "active_part_data", None)
        if part_data is None:
            self.controller.after(0, lambda: messagebox.showerror("Error", "No part selected. Please login first."))
            return

        part = part_data["name"]
        self.controller.after(0, lambda: self.part_label.config(
            text=f"Inspecting: {part_data['name']}\n{part_data['description']}"
        ))

        paths = get_paths(part)

        if not os.path.exists(paths["reference"]) or not os.path.exists(paths["roi"]):
            self.controller.after(0, lambda: messagebox.showerror("Error", "Reference image or ROIs missing."))
            return

        try:
            with open(paths["roi"], "r") as f:
                rois = json.load(f)["rois"]
        except Exception as e:
            self.controller.after(0, lambda: messagebox.showerror("Error", f"Failed to load ROIs: {e}"))
            return

        ref = cv2.imread(paths["reference"])

        with camera_lock:
            init_camera()
            if global_camera is None:
                self.controller.after(0, lambda: messagebox.showerror("Error", "Camera not initialized."))
                return
                
            ret, frame = global_camera.read()
            frame = apply_zoom(frame, zoom_factor=1)

        if not ret:
            self.controller.after(0, lambda: messagebox.showerror("Error", "Failed to capture frame."))
            return

        ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        live_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        result = frame.copy()

        all_ok = True
        for entry in rois:
            x, y, w, h = entry["rect"]
            threshold = entry["threshold"]
            name = entry.get("name", "ROI")

            ref_roi = ref_gray[y:y + h, x:x + w]
            live_roi = live_gray[y:y + h, x:x + w]

            if live_roi.shape != ref_roi.shape:
                live_roi = cv2.resize(live_roi, (ref_roi.shape[1], ref_roi.shape[0]))

            try:
                score = ssim(ref_roi, live_roi)
            except Exception:
                score = 0.0

            label = "OK" if score >= threshold else "NG"
            status_color = "lime" if label == "OK" else "red"
            border_color = "#00FF00" if label == "OK" else "#FF0000"
            border_color1 = (0, 255, 0) if label == "OK" else (0, 0, 255)
            
            if label != "OK":
                all_ok = False
                
            cv2.rectangle(result, (x, y), (x + w, y + h), border_color1, 2)
            cv2.putText(result, f"{name}:{label}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, border_color1, 2)

            roi_thumbnail = cv2.resize(live_roi, (50, 50))
            roi_thumbnail_rgb = cv2.cvtColor(roi_thumbnail, cv2.COLOR_GRAY2RGB)
            roi_img_pil = Image.fromarray(roi_thumbnail_rgb)
            roi_img_tk = ImageTk.PhotoImage(roi_img_pil)
            self._image_refs.append(roi_img_tk)  # Safe reference holding

            status_text = f"{name}: {label} ({score * 100:.1f}%)"

            def make_roi_widget(img=roi_img_tk, text=status_text, color=status_color, border=border_color):
                roi_frame = tk.Frame(self.roi_status_frame, bg="#1e1e1e")
                roi_frame.pack(anchor="w", pady=2, padx=5, fill="x")

                canvas = tk.Canvas(roi_frame, width=54, height=54, bg="#1e1e1e", highlightthickness=0)
                canvas.pack(side="left", padx=(0, 10))
                canvas.create_rectangle(2, 2, 52, 52, outline=border, width=2)
                canvas.create_image(27, 27, image=img)

                text_label = tk.Label(roi_frame, text=text, fg=color, bg="#1e1e1e", font=("Arial", 12))
                text_label.pack(side="left", anchor="w")

            self.controller.after(0, make_roi_widget)

        overall = "OK" if all_ok else "NG"
        overall_color = "lime" if all_ok else "red"
        self.controller.after(0, lambda: self.overall_status.config(text=overall, fg=overall_color))
        
        if all_ok:
            now = datetime.datetime.now()
            hour = now.hour
            shift = "A" if 7 <= hour < 19 else "B"
            timestamp = now.strftime("%d-%m-%y")

            tspl_command = f"""
            <xpml><page quantity='0' pitch='14.0 mm'></xpml>SIZE 13.10 mm, 14 mm
            GAP 3 mm, 0 mm
            DIRECTION 0,0
            REFERENCE 0,0
            OFFSET 0 mm
            SET PEEL OFF
            SET CUTTER OFF
            SET PARTIAL_CUTTER OFF
            <xpml></page></xpml><xpml><page quantity='1' pitch='14.0 mm'></xpml>SET TEAR ON
            CLS
            QRCODE 88,88,L,3,A,180,M2,S7,"OV64-CR3-J4U{part_data['name']} {timestamp} {shift}"
            CODEPAGE 1252
            TEXT 107,5,"ROMAN.TTF",90,1,6,"OV64 CR3 J4U"
            TEXT 81,107,"ROMAN.TTF",180,1,6,"{part_data['description']}"
            PRINT 1,1
            <xpml></page></xpml><xpml><end/></xpml>
            """
            success, msg = send_tspl_command_to_printer("TSC_TE210", tspl_command)
            if not success:
                print("Printer Error:", msg)

        resized = cv2.resize(result, (800, 600))
        rgb_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb_image))
        self._image_refs.append(img)

        self.controller.after(0, lambda: self.image_label.configure(image=img))

        GPIO.output(OK_PIN, GPIO.HIGH if all_ok else GPIO.LOW)
        GPIO.output(NG_PIN, GPIO.LOW if all_ok else GPIO.HIGH)


# ------------------------ AdminPage ------------------------
class AdminPage(tk.Frame):
    def resize_canvas_image(self, event):
        if self.image is None:
            return

        canvas_width = event.width
        canvas_height = event.height

        resized_image = cv2.resize(self.image, (canvas_width, canvas_height))
        img_rgb = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(img_rgb))
        self._image_refs.append(self.tk_image)

        self.canvas.delete("all")  
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

    def open_virtual_keyboard_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Enter ROI Info")
        dialog.geometry("400x500")
        dialog.configure(bg="#2c2c2c")

        tk.Label(dialog, text="ROI Name:", bg="#2c2c2c", fg="white").pack(pady=5)
        name_entry = tk.Entry(dialog, font=("Arial", 12))
        name_entry.pack(pady=5)

        tk.Label(dialog, text="Threshold (0-1):", bg="#2c2c2c", fg="white").pack(pady=5)
        threshold_entry = tk.Entry(dialog, font=("Arial", 12))
        threshold_entry.pack(pady=5)

        input_target = {"entry": name_entry} 

        def insert_char(char):
            entry = input_target["entry"]
            entry.insert(tk.END, char)

        def backspace():
            entry = input_target["entry"]
            current = entry.get()
            entry.delete(0, tk.END)
            entry.insert(0, current[:-1])

        def set_focus(entry_widget):
            input_target["entry"] = entry_widget

        name_entry.bind("<FocusIn>", lambda e: set_focus(name_entry))
        threshold_entry.bind("<FocusIn>", lambda e: set_focus(threshold_entry))

        keyboard_frame = tk.Frame(dialog, bg="#2c2c2c")
        keyboard_frame.pack(pady=10)

        keys = [
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
            ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
            ['.', '_', '-', 'Backspace']
        ]

        for row in keys:
            row_frame = tk.Frame(keyboard_frame, bg="#2c2c2c")
            row_frame.pack(pady=2)
            for key in row:
                if key == "Backspace":
                    b = tk.Button(row_frame, text=key, width=10, command=backspace)
                else:
                    b = tk.Button(row_frame, text=key, width=4, command=lambda c=key: insert_char(c))
                b.pack(side="left", padx=2)

        result = {}

        def on_submit():
            name = name_entry.get().strip()
            try:
                threshold = float(threshold_entry.get())
                if not (0.0 <= threshold <= 1.0):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid Threshold", "Threshold must be a number between 0 and 1.")
                return

            if not name:
                messagebox.showerror("Invalid Name", "ROI Name cannot be empty.")
                return

            result["name"] = name
            result["threshold"] = threshold
            dialog.destroy()

        submit_btn = tk.Button(dialog, text="OK", command=on_submit, bg="green", fg="white", font=("Arial", 12))
        submit_btn.pack(pady=15)

        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        self.wait_window(dialog)

        return result if "name" in result else None

    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller
        self.rois = []
        self.rectangles = []
        self._image_refs: List[Any] = []

        self.image = None
        self.tk_image = None
        self.start_x = self.start_y = 0
        self.current_rect = None

        left_frame = tk.Frame(self, bg="#1e1e1e")
        right_frame = tk.Frame(self, bg="#2c2c2c", width=300)

        left_frame.pack(side="left", fill="both", expand=True)
        right_frame.pack(side="right", fill="y")

        tk.Label(left_frame, text="Admin Panel", font=("Arial", 18), bg="#1e1e1e", fg="white").pack(pady=10)

        top_button_frame = tk.Frame(left_frame, bg="#1e1e1e")
        top_button_frame.pack(side="top", fill="x", pady=(10, 0))

        button_specs = [
            ("Capture Reference", self.capture_reference),
            ("Select ROIs", self.load_reference_to_canvas),
            ("Clear ROIs", self.clear_rois),
            ("Save ROIs", self.save_rois),
            ("Back", lambda: controller.show_frame(LoginPage)),
        ]

        for (text, cmd) in button_specs:
            tk.Button(top_button_frame, text=text, command=cmd, bg="#444444", fg="white", activebackground="#555555", activeforeground="white").pack(side="left", padx=5)

        self.canvas = tk.Canvas(left_frame, bg="#2c2c2c", highlightthickness=0)
        self.canvas.pack(side="top", fill="both", expand=True, pady=10)

        left_frame.pack_propagate(False)

        self.canvas.bind("<Configure>", self.resize_canvas_image)
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        tk.Label(right_frame, text="ROIs & Thresholds", font=("Arial", 14), bg="#2c2c2c", fg="white").pack(pady=(10, 5))
        self.roi_list_frame = tk.Frame(right_frame, bg="#2c2c2c")
        self.roi_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def capture_reference(self):
        paths = get_paths(getattr(self.controller, "active_part", ""))
        success, result = capture_frame_to_file(paths["reference"], zoom_factor=1)
        if success:
            messagebox.showinfo("Success", "Reference image captured.")
        else:
            messagebox.showerror("Error", f"Capture failed: {result}")

    def load_reference_to_canvas(self):
        self.clear_canvas_graphics_only()
        paths = get_paths(getattr(self.controller, "active_part", ""))
        self.image = cv2.imread(paths["reference"])
        if self.image is None:
            messagebox.showerror("Error", "Reference image not found.")
            return

        self.display_image = cv2.resize(self.image, (800, 600))
        img_rgb = cv2.cvtColor(self.display_image, cv2.COLOR_BGR2RGB)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(img_rgb))
        self._image_refs.append(self.tk_image)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

        try:
            with open(paths["roi"], "r") as f:
                self.rois = json.load(f)["rois"]
        except Exception:
            self.rois = []

        for widget in self.roi_list_frame.winfo_children():
            widget.destroy()

        scale_x = 800 / self.image.shape[1]
        scale_y = 600 / self.image.shape[0]

        for roi in self.rois:
            self.add_roi_to_list_ui(roi)
            x, y, w, h = roi["rect"]
            x1 = int(x * scale_x)
            y1 = int(y * scale_y)
            x2 = int((x + w) * scale_x)
            y2 = int((y + h) * scale_y)
            color = "green" if roi["threshold"] >= 0.9 else "orange" if roi["threshold"] >= 0.7 else "red"

            rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
            label = self.canvas.create_text(x1 + 5, y1 + 15, anchor="nw", text=roi["name"], fill="white", font=("Arial", 10))
            self.rectangles.append(rect)
            self.rectangles.append(label)

    def on_mouse_down(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.current_rect = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="yellow", width=2)

    def on_mouse_drag(self, event):
        if self.current_rect is not None:
            self.canvas.coords(self.current_rect, self.start_x, self.start_y, event.x, event.y)

    def on_mouse_up(self, event):
        if self.image is None or self.current_rect is None:
            return

        end_x, end_y = event.x, event.y
        x1, y1 = min(self.start_x, end_x), min(self.start_y, end_y)
        x2, y2 = max(self.start_x, end_x), max(self.start_y, end_y)

        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            self.canvas.delete(self.current_rect)
            return

        scale_x = self.image.shape[1] / 800
        scale_y = self.image.shape[0] / 600

        rect_x = int(x1 * scale_x)
        rect_y = int(y1 * scale_y)
        rect_w = int((x2 - x1) * scale_x)
        rect_h = int((y2 - y1) * scale_y)

        input_data = self.open_virtual_keyboard_dialog()
        if not input_data:
            if self.current_rect is not None:
                self.canvas.delete(self.current_rect)
            return

        name = input_data["name"]
        threshold = input_data["threshold"]

        roi = {"name": name, "rect": [rect_x, rect_y, rect_w, rect_h], "threshold": threshold}
        self.rois.append(roi)
        self.add_roi_to_list_ui(roi)

        label = self.canvas.create_text(x1 + 5, y1 + 15, anchor="nw", text=name, fill="white", font=("Arial", 10))
        self.rectangles.append(self.current_rect)
        self.rectangles.append(label)
        self.current_rect = None

    def add_roi_to_list_ui(self, roi):
        frame = tk.Frame(self.roi_list_frame, bg="#2c2c2c")
        frame.pack(fill="x", pady=2)

        tk.Label(frame, text=roi["name"], bg="#2c2c2c", fg="white", font=("Arial", 10)).pack(side="left", padx=5)

        threshold_label = tk.Label(frame, text=f"Threshold: {roi['threshold']:.2f}", bg="#2c2c2c", fg="white",
                                   font=("Arial", 10), cursor="hand2")
        threshold_label.pack(side="right", padx=5)
        threshold_label.bind("<Button-1>", lambda e: self.edit_threshold_inline(roi, threshold_label))

    def edit_threshold_inline(self, roi, label_widget):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Threshold")
        dialog.geometry("300x400")
        dialog.configure(bg="#2c2c2c")

        tk.Label(dialog, text=f"Edit Threshold for {roi['name']}", bg="#2c2c2c", fg="white", font=("Arial", 12)).pack(pady=10)

        entry = tk.Entry(dialog, font=("Arial", 16), justify="center")
        entry.insert(0, str(roi["threshold"]))
        entry.pack(pady=10, ipadx=10, ipady=5)

        def insert_char(c):
            entry.insert(tk.END, c)

        def backspace():
            current = entry.get()
            entry.delete(0, tk.END)
            entry.insert(0, current[:-1])

        def clear():
            entry.delete(0, tk.END)

        numpad_keys = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['0', '.', '?'],
            ['Clear']
        ]

        keypad_frame = tk.Frame(dialog, bg="#2c2c2c")
        keypad_frame.pack()

        for row in numpad_keys:
            row_frame = tk.Frame(keypad_frame, bg="#2c2c2c")
            row_frame.pack(pady=3)
            for key in row:
                if key == "?":
                    b = tk.Button(row_frame, text=key, width=5, height=2, command=backspace)
                elif key == "Clear":
                    b = tk.Button(row_frame, text=key, width=18, height=2, command=clear)
                else:
                    b = tk.Button(row_frame, text=key, width=5, height=2, command=lambda c=key: insert_char(c))
                b.pack(side="left", padx=2)

        def on_submit():
            try:
                val = float(entry.get())
                if 0.0 <= val <= 1.0:
                    roi["threshold"] = val
                    label_widget.config(text=f"Threshold: {val:.2f}")
                    dialog.destroy()
                else:
                    messagebox.showerror("Invalid", "Enter a value between 0 and 1.")
            except ValueError:
                messagebox.showerror("Invalid", "Enter a numeric value.")

        submit_btn = tk.Button(dialog, text="OK", command=on_submit, bg="green", fg="white", font=("Arial", 12))
        submit_btn.pack(pady=15)

        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        self.wait_window(dialog)

    def clear_rois(self):
        self.rois = []
        self.clear_canvas_graphics_only()
        for widget in self.roi_list_frame.winfo_children():
            widget.destroy()

    def clear_canvas_graphics_only(self):
        for item in self.rectangles:
            self.canvas.delete(item)
        self.rectangles = []

    def save_rois(self):
        paths = get_paths(getattr(self.controller, "active_part", ""))
        try:
            with open(paths["roi"], "w") as f:
                json.dump({"rois": self.rois}, f, indent=2)
            messagebox.showinfo("Saved", "ROIs saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save ROIs: {e}")


# ------------------------ LoginPage ------------------------
class LoginPage(tk.Frame):
    def shutdown_pi(self):
        confirm = messagebox.askyesno("Confirm Shutdown", "Are you sure you want to shut down?")
        if confirm:
            self.controller.destroy()
            os.system("sudo shutdown -h now")

    def reboot_pi(self):
        confirm = messagebox.askyesno("Confirm Reboot", "Are you sure you want to reboot?")
        if confirm:
            self.controller.destroy()
            os.system("sudo reboot")

    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller

        tk.Label(self, text="Login", font=("Arial", 20), bg="#1e1e1e", fg="white").pack(pady=10)

        tk.Label(self, text="Username", bg="#1e1e1e", fg="white").pack()
        self.username_entry = tk.Entry(self, font=("Arial", 14), bg="#333333", fg="white", insertbackground="white")
        self.username_entry.pack(pady=5)

        tk.Label(self, text="Password", bg="#1e1e1e", fg="white").pack()
        self.password_entry = tk.Entry(self, show="*", font=("Arial", 14), bg="#333333", fg="white", insertbackground="white")
        self.password_entry.pack(pady=5)

        tk.Label(self, text="Select Part", bg="#1e1e1e", fg="white").pack(pady=(10, 0))

        try:
            with open("parts.json", "r") as f:
                parts_data = json.load(f)["parts"]
        except Exception:
            parts_data = [{"name": "9873138380-LT", "description": "Default part description"}]

        self.parts_data = parts_data
        self.part_names = [p["name"] for p in parts_data]
        self.part_var = tk.StringVar(value=self.part_names[0])

        option_menu = tk.OptionMenu(self, self.part_var, *self.part_names)
        option_menu.configure(bg="#333333", fg="white", highlightbackground="#1e1e1e")
        option_menu.pack(pady=5)

        self.description_label = tk.Label(self, text="", bg="#1e1e1e", fg="gray", wraplength=400, justify="center")
        self.description_label.pack(pady=5)

        def update_description(*args):
            selected = self.part_var.get()
            for part in self.parts_data:
                if part["name"] == selected:
                    self.description_label.config(text=part["description"])
                    break

        self.part_var.trace_add("write", update_description)
        update_description()

        self.focused_entry = self.username_entry
        self.username_entry.bind("<FocusIn>", lambda e: self.set_focus(self.username_entry))
        self.password_entry.bind("<FocusIn>", lambda e: self.set_focus(self.password_entry))

        self.create_keypad()
        tk.Button(self, text="Login", command=self.login, height=2, width=20, bg="#444444", fg="white").pack(pady=10)
        tk.Button(self, text="Shutdown", command=self.shutdown_pi, height=2, width=20, bg="#aa3333", fg="white").pack(pady=5)
        tk.Button(self, text="Reboot", command=self.reboot_pi, height=2, width=20, bg="#3366cc", fg="white").pack(pady=5)
        
        tk.Label(self, text="AV TECH AUTOMATION & ENERGY SOLUTION", bg="#1e1e1e", fg="gray", font=("Arial", 15)).place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

    def set_focus(self, widget):
        self.focused_entry = widget

    def create_keypad(self):
        keypad = tk.Frame(self, bg="#1e1e1e")
        keypad.pack(pady=10)

        keys = [
            ('1', 1, 0), ('2', 1, 1), ('3', 1, 2),
            ('4', 2, 0), ('5', 2, 1), ('6', 2, 2),
            ('7', 3, 0), ('8', 3, 1), ('9', 3, 2),
            ('C', 4, 0), ('0', 4, 1), ('<', 4, 2),
        ]

        for (text, row, col) in keys:
            btn = tk.Button(keypad, text=text, width=5, height=2, font=("Arial", 12),
                            bg="#444444", fg="white",
                            command=lambda t=text: self.on_keypad_press(t))
            btn.grid(row=row, column=col, padx=5, pady=5)

    def on_keypad_press(self, key):
        if not self.focused_entry:
            return
        if key == 'C':
            self.focused_entry.delete(0, tk.END)
        elif key == '<':
            current = self.focused_entry.get()
            self.focused_entry.delete(0, tk.END)
            self.focused_entry.insert(0, current[:-1])
        else:
            self.focused_entry.insert(tk.END, key)

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        selected_name = self.part_var.get()
        for part in self.parts_data:
            if part["name"] == selected_name:
                self.controller.active_part = part["name"]
                self.controller.active_part_data = part
                break

        if username == "1" and password == "1":
            self.controller.show_frame(AdminPage)
        elif (username == "2" and password == "2") or (username == "03" and password == "3333"):
            self.controller.username = username
            self.controller.show_frame(InspectorPage)
        else:
            messagebox.showerror("Error", "Invalid credentials")

# ------------------------ Main Application ------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("1280x720")
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.configure(bg="#1e1e1e")
        
        self.active_part = None
        self.active_part_data = None

        self.container = tk.Frame(self, bg="#1e1e1e")
        self.container.pack(fill="both", expand=True)

        self.frames = {}
        
        self.parts_list = [ 
            {"name": "9873138380-LT", "description": "8380-LT"},
            {"name": "9873138180-RT", "description": "8180-RT"},
            {"name": "9846995080-RT", "description": "5080-RT"},
            {"name": "9873138980-RT", "description": "8980-RT"}
        ]

        for F in (LoginPage, AdminPage, InspectorPage):
            frame = F(self.container, self)
            self.frames[F] = frame
            frame.place(relwidth=1, relheight=1)

        self.show_frame(LoginPage)

    def get_part_data_by_name(self, name):
        for part in self.parts_list:
            if part["name"].lower() == name.lower():
                return part
        return None

    def show_frame(self, page):
        frame = self.frames[page]
        frame.tkraise()
        if page in (AdminPage, InspectorPage) and hasattr(frame, "refresh"):
            frame.refresh()

if __name__ == "__main__":
    app = None
    try:
        init_camera()
        app = App()
        app.mainloop()
    finally:
        if app is not None:
            for frame in app.frames.values():
                if isinstance(frame, InspectorPage):
                    frame.running = False 
        time.sleep(0.5) 
        GPIO.cleanup()
        if global_camera and global_camera.isOpened():
            global_camera.release()