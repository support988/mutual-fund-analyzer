import os
import subprocess
import shutil
import sys

def build_exe(entry_point, name, windowed=True, datas=None):
    print(f"\n{'='*50}")
    print(f"Building: {name}")
    print(f"Entry Point: {entry_point}")
    print(f"{'='*50}")
    
    # Base command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--clean",
        f"--name={name}",
    ]
    
    if windowed:
        cmd.append("--windowed")
    else:
        cmd.append("--console")
        
    # Add data files
    if datas:
        for src, dest in datas:
            # On Windows, separator is ;
            cmd.append(f"--add-data={src};{dest}")
            
    # Add entry point
    cmd.append(entry_point)
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"\nSuccessfully built {name}.exe in dist folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nError building {name}: {e}")
        return False
    return True

def main():
    # Change to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # List of applications to build
    apps = [
        {
            "entry_point": "main.py",
            "name": "MF_Portfolio_Tracker",
            "windowed": True,
            "datas": [("config.json", ".")]
        },
        {
            "entry_point": "test_pyqt.py",
            "name": "Test_PyQt_Env",
            "windowed": False, # Console for testing
            "datas": []
        }
    ]
    
    # Clean previous builds
    folders_to_clean = ["build", "dist"]
    for folder in folders_to_clean:
        if os.path.exists(folder):
            print(f"Cleaning {folder}...")
            shutil.rmtree(folder)
            
    # Remove old spec files
    for file in os.listdir("."):
        if file.endswith(".spec"):
            os.remove(file)

    success_count = 0
    for app in apps:
        if build_exe(**app):
            success_count += 1
            
    print(f"\n{'='*50}")
    print(f"Build process completed.")
    print(f"Successfully built {success_count} out of {len(apps)} executables.")
    print(f"Check the 'dist' folder for the generated files.")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
