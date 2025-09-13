import tkinter as tk
import subprocess
import os
import sys

def run_jav_script():
    script_path = os.path.join(os.path.dirname(__file__), "Jav+Preview.py")
    subprocess.Popen([sys.executable, script_path])

def run_western_script():
    script_path = os.path.join(os.path.dirname(__file__), "Western+preview.py")
    subprocess.Popen([sys.executable, script_path])

def main():
    root = tk.Tk()
    root.title("Media Processor Launcher")
    root.geometry("300x150")
    root.eval('tk::PlaceWindow . center')

    tk.Label(root, text="Select which processor to run:", font=("Arial", 12)).pack(pady=10)

    tk.Button(root, text="Jav Processor", command=run_jav_script, font=("Arial", 10), width=20).pack(pady=5)
    tk.Button(root, text="Western Processor", command=run_western_script, font=("Arial", 10), width=20).pack(pady=5)

    root.mainloop()

if __name__ == "__main__":
    main()
