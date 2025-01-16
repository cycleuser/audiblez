# ...existing code...
import os
import subprocess

# Change working directory to the script's directory
current_file_path = os.path.abspath(__file__)
current_directory = os.path.dirname(current_file_path)
os.chdir(current_directory)

for filename in os.listdir('.'):
    if filename.lower().endswith('.epub'):
        cmd = ["audiblez", filename, "-l", "en-gb", "-v", "af_sky", "-s", "1.0"]
        print(f"Processing {filename} with command: {cmd}")
        subprocess.run(cmd)