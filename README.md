
Linux file search application with hybrid analysis
<p>
Save encrypted notes <br>
Quick commands displays saved commands for easy reference <br>
Create a custom crest with a .png image file max size 255 x 333 <br>
Full commandline support with recentchanges being in path<br>

Build a system profile to compare during hybrid analysis as well as a system index scan <br>
Features system profile by .xzm for porteus linux <br>
</p><br>

## Installation
cd /usr/local/recentchanges <br>
python -m venv .venv <br>
source .venv/bin/activate <br>
python -m pip install --upgrade pi <br>
pip install -r requirements.txt <br>
python main.py <br>

adjust if missing any <br><br>
pip install dependency

optionally can install the required packages in system using package manager

main dependencies <br>
PySide6-Essentials<br>
tomlkit <br>
python-magic <br>
psutil <br>
requests <br>
packaging <br>
pillow <br>
pyudev <br><br>


## PyInstaller<br>
to build a binary from the venv above <br>
pip install pyinstaller <br>
python3 -m PyInstaller --clean --noconfirm main.spec <br>
copy main and _internal from dist/main folder to /usr/local/recentchanges
./main
optionally remove src/ and main.py
<br><br>
If cant find command recentchanges move /usr/local/bin/recentchanges somewhere in path ie for porteus needs to be in /opt/porteus-scripts/ <br><br>
![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>


