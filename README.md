Version 6.0.0 released! <br>
updated to work with only user pinentry configured <br>
new bash launcher and helper script and ensured proper operation with venv or system <br><br>

While I could distribute just a binary I believe this is the better way. It can be used with just python
or build it into a binary with pyinstaller from the same release. All that has to be changed is a few scripts
copied from the pyinstaller release. Or just built from the pyinstaller release

I am now focusing on just linux and researching how I can reshape and retool recentchanges to be more responsive and adapt to
modern approaches at gui distribution. 


![Alt text](https://i.imgur.com/gqbO4HB.png) <br>

Linux file search application with hybrid analysis <br><br>


<p>
Check for hash collisions during search <br>
Save encrypted notes <br>
Quick commands displays saved commands for easy reference <br>
Create a custom crest with a .png image file max size 255 x 333 <br>

Build a system profile to compare during hybrid analysis as well as a system index scan <br>
Features system profile by .xzm for porteus linux <br>
</p><br>
requirements: find 4.8.0 gnupg 2 and pinentry  <br><br>

Full commandline support with recentchanges being in path<br>
recentchanges <br>
recentchanges search <br>
recentchanges gui <br>
recentchanges query <br>
recentchanges reset <br><br>

can be run from venv or system install

python -m venv .venv <br>
source .venv/bin/activate <br>
python -m pip install --upgrade pip <br>
pip install -r requirements.txt <br>
python main.py <br><br>

## System Install
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
optionally can install the required packages in system using package manager. nemesis may require xcb-util-cursor xcb-util-keysyms xcb-util-wm<br><br>

requires gpg setup as user <br>
While testing nemesis the follow step wasnt needed but may be needed to get pinentry working <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent <br>
then as root <br>

see [gpg setup](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.kotw1gextu63) for troubleshooting <br><br>
things to do after installation: chown root:root /usr/local/recentchanges <br>
the reason it is owned by guest:users is so pyinstaller has permission to build <br><br>
## Pyinstaller <br>
This version can be built with pyinstaller with main.spec. if building the launcher script /usr/local/bin/recentchanges and polkit have to be changed. <br><br>
in /usr/local/bin/recentchanges change python3 "$app_install"/src/rntchanges.py to "$app_install"/main in the two areas <br><br>
then in /usr/local/recentchanges/scripts/rntchangesfunctions ln119 to "$app_install"/main and line below <br><br>
and<br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy   ln14 <br>
change to /usr/local/recentchanges/main <br><br>

or

replace the following files from pyinstaller source: <br>
/usr/local/bin/recentchanges <br>
/usr/local/recentchanges/scripts/rntchangesfunctions <br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy <br><br>

or <br>
use pyinstaller version with changes made <br>

<p> remember to chown root:root /usr/local/recentchanges as a last step. default is guest:users for owner for pyinstaller build </p>

PyInstaller<br>
https://github.com/dreadwrr/Linux-Pyinstaller <br>
to build a binary with all the packages and not needing any on the system <br><br>

the filter used is for nemesis 25.04 <br>
porteus configured filter https://drive.google.com/file/d/11MjrAc4rgfH3GR1sFTUkf4WsV4amcBOy/view?usp=sharing <br>
picture for graphic https://i.imgur.com/UoL7CHQ.jpeg<br><br>
ui source file https://drive.google.com/file/d/1ndV65m31pbRN7oFnh1ut4z867GPm7rYr/view?usp=sharing<br>

<br>
Manual
https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0  
Porteus forums
https://forum.porteus.org/  <br><br>

This project has helped me learn python and about linux. The primary focus is always
minimal requirements and custom logic. So check in from time to time as I come up with new features and enhance recent changes.

![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>
