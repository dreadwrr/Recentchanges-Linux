
Linux file search application with hybrid analysis
<p>
Save encrypted notes <br>
Quick commands displays saved commands for easy reference <br>
Create a custom crest with a .png image file max size 255 x 333 <br>
Full commandline support with recentchanges being in path<br>

Build a system profile to compare during hybrid analysis as well as a system index scan <br>
Features system profile by .xzm for porteus linux <br>
</p><br>
requirements: find 4.8.0 gnupg 2 and pinentry  <br>

## Installation
install pip with package manager <br>
cd /usr/local/recentchanges <br>
pip install PySide6 <br>
pip install tomlkit <br>
pip install python-magic <br>
pip install psutil <br>
pip install requests <br>
pip install packaging <br>
pip install pillow <br>
pip install pyudev <br>
python main.py <br><br>
adjust if missing any<br>
optionally can install the required packages in system using package manager


## PyInstaller<br>
Note: i will put a seperate repo as the configuration for pyinstaller requires different paths<br>
use installation above until the repo is posted <br><br>
to build a binary with all the packages and not needing any on the system <br>
cd /usr/local/recentchanges <br>
chown guest:users /usr/local/recentchanges <br>
python -m venv .venv <br>
source .venv/bin/activate <br>
python -m pip install --upgrade pi <br>
pip install -r requirements.txt <br>
pip install pyinstaller <br>
pyinstaller --onedir main.py --collect-all=libshiboken <br>
copy main and _internal from dist/main folder to /usr/local/recentchanges ./main <br> 
optionally remove src/ and main.py <br><br>

compatibility if the above fails again from the venv<br>
python3 -m PyInstaller --clean --noconfirm main.spec <br><br>
if there is an error about webengine add to main.spec <br>
    excludes=[ <br>
        'tkinter', <br>
        'PySide6.QtWebEngine', <br>
        'PySide6.QtWebEngineWidgets', <br>
        'PySide6.QtWebEngineCore', <br>
        'PySide6.QtMultimedia', <br>
        'PySide6.QtCharts', <br>
        'PySide6.QtPrintSupport', <br>
	], <br>
<br>
If cant find command recentchanges move /usr/local/bin/recentchanges somewhere in path ie for porteus needs to be in /opt/porteus-scripts/ <br>
![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>


