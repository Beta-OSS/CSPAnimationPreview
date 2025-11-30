import os
import glob
import tkinter as tk
from PIL import Image, ImageTk
from extract_frames import extract_layers

# Fixed window size
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
SCALE_FACTOR = 0.9  # Slightly smaller than window

# Extract frames
clip_file = "fox.clip"
output_dir, temp_dir = extract_layers(clip_file)

# Load frames
png_files = sorted(glob.glob(os.path.join(output_dir, "*.png")))
frames = [Image.open(f) for f in png_files]

# Tkinter setup
root = tk.Tk()
root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
root.resizable(False, False)  # Fix window size
label = tk.Label(root)
label.pack(expand=True)

frame_index = 0
playing = True

def resize_frame(frame):
    max_width = int(WINDOW_WIDTH * SCALE_FACTOR)
    max_height = int(WINDOW_HEIGHT * SCALE_FACTOR)

    frame_ratio = frame.width / frame.height
    max_ratio = max_width / max_height

    if frame_ratio > max_ratio:
        new_width = max_width
        new_height = int(max_width / frame_ratio)
    else:
        new_height = max_height
        new_width = int(max_height * frame_ratio)

    return frame.resize((new_width, new_height), Image.LANCZOS)

def show_frame():
    global frame_index
    frame = resize_frame(frames[frame_index])
    tk_frame = ImageTk.PhotoImage(frame)
    label.config(image=tk_frame)
    label.image = tk_frame

def animate():
    global frame_index
    if playing:
        frame_index = (frame_index + 1) % len(frames)
        show_frame()
    root.after(100, animate)

# Buttons
def toggle_play():
    global playing
    playing = not playing

def forward_frame():
    global frame_index
    frame_index = (frame_index + 1) % len(frames)
    show_frame()

def backward_frame():
    global frame_index
    frame_index = (frame_index - 1) % len(frames)
    show_frame()

button_frame = tk.Frame(root)
button_frame.pack(side="bottom", pady=5)
tk.Button(button_frame, text="⏮", command=backward_frame).pack(side="left")
tk.Button(button_frame, text="⏯", command=toggle_play).pack(side="left")
tk.Button(button_frame, text="⏭", command=forward_frame).pack(side="left")

show_frame()
animate()
root.mainloop()

# Cleanup temp folder
if temp_dir:
    temp_dir.cleanup()
