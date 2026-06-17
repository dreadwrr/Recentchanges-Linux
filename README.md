Released 6.1.2!

Added LCD alarm clock
Changed the way the find command is run and other ease of use improvements

![Alt text](https://i.imgur.com/gqbO4HB.png) <br>

Linux file search application with hybrid analysis <br>

<p>
Check for hash collisions during search <br>
Save encrypted notes <br>
Quick commands displays saved commands for easy reference <br>
Create a custom crest with a .png image file max size 255 x 333 <br>

Build a system profile to compare during hybrid analysis as well as a system index scan <br>
Features system profile by .xzm for porteus linux <br>
</p><br>

requirements: find 4.8.0 gnupg 2 and pinentry  <br><br>

Full commandline support with recentchanges being in path<br><br>

commands: <br>
recentchanges <br>
recentchanges search <br>
recentchanges gui <br>
recentchanges query <br>
recentchanges reset <br><br>

## Installation instructions

on first activation log out and log back in to see menu icon. then to add polkit policies without needing to reboot <br>
pkill polkitd

1. note the following step wasnt needed for nemesis but is for porteus <br><br>
requires gpg setup as user <br>
```
mkdir ~/.gnupg && chmod 700 ~/.gnupg
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf
gpgconf --kill gpg-agent
```

2. setup a virtual environment from menu icon or command recentchanges gui 

or

cd /usr/local/recentchanges <br>
python -m venv .venv <br>
source .venv/bin/activate <br>
python -m pip install --upgrade pip <br>
pip install -r requirements.txt <br>
python main.py <br><br>

see [gpg setup](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.kotw1gextu63) for troubleshooting <br><br>

as a last step <br> 
chown root:root /usr/local/recentchanges if not using pyinstaller <br><br>

## System Install

Another method to install is by packages on system

This will cover the installation for nemesis. [porteus install instructions](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.4bfen5md1n9x) here. or with [pip installation](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.alk9y51grswe)<br><br>
This step is optional first try running and come back if needing pinentry setup <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent <br><br>
cd /usr/local/recentchanges <br>
use pman -Sw for the packages <br>
pyside6 <br>
python-pyudev <br>
python-psutil <br>
python-magic <br>
python-pillow <br>
python-tomlkit <br><br>
may require packaging and requests package see requirements.txt if needing to adjust <br><br>
python main.py <br><br>
tested on nemesis and xcb-util was needed for qt <br>
pman -Sw xcb-util-cursor <br>
pman -Sw xcb-util-keysyms <br>
pman -Sw xcb-util-wm <br><br>
see [gpg setup](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.kotw1gextu63) for troubleshooting <br><br>
things to do after installation: chown root:root /usr/local/recentchanges <br>
the reason it is owned by guest:users is so pyinstaller has permission to build <br><br>
## Pyinstaller <br>
This version can be built with pyinstaller with main.spec. to build a binary with all the packages and not needing any on the system <br><br>
build from steps at PyInstaller repo<br>
https://github.com/dreadwrr/Linux-Pyinstaller <br><br>


then launcher script /usr/local/bin/recentchanges and polkit have to be changed. <br><br>
1. in /usr/local/bin/recentchanges change python3 "$app_install"/src/rntchanges.py to "$app_install"/main in the two areas <br><br>
2. then in /usr/local/recentchanges/scripts/rntchangesfunctions ln119 to "$app_install"/main and line below <br><br>

3. /usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy   ln14 <br>
change to /usr/local/recentchanges/main <br><br>

or

replace the following files from pyinstaller source: <br>
/usr/local/bin/recentchanges <br>
/usr/local/recentchanges/scripts/rntchangesfunctions <br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy <br><br>

or

use pyinstaller version with changes made <br><br>


<p> chown root:root /usr/local/recentchanges </p>
<br><br>

## Troubleshooting

will add things here with plans to automate them on later updates <br><br>

If having problem with config file and fails to load it could be a old mismatch between version or with incorrect keys <br>
remove from <br>
~/.config/recentchanges/ <br><br>
command recentchanges reset can be used to remove the gpg key and .gpg files to clear possible key conflicts. The next release will have the
config clear prompt <br><br>


##
picture for graphic https://i.imgur.com/UoL7CHQ.jpeg<br><br>
ui source file https://drive.google.com/file/d/1TjprEuGbD-yBa4R6ep6o9CFI91Ypgn0R/view?usp=sharing<br>
<br>
Manual [Google docs](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0)  
Porteus forums
https://forum.porteus.org/  <br><br>

This project has helped me learn python and about linux. The primary focus is always
minimal requirements and custom logic. So check in from time to time as I come up with new features and enhance recent changes.

![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>
