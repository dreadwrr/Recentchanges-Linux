![Alt text](https://i.imgur.com/p1kuXYp.png) <br>
5.0.9 Released with a menu icon and launcher script with automated setup <br>
command recentchanges gui can launch Qt app or menu icon <br>
5.0.8<br>
Added the changes from the repo for drive logic for spinner and dynamic config. <br>
Move rnt symlink to not conflict with other modules <br><br>
5.0.7 added key optimizations and drive logic. Added environment variable to launcher. <br> One step py installer build if preferred <br><br>

Linux file search application with hybrid analysis <br><br>


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
optionally can install the required packages in system using package manager<br><br>

gpg setup <br>
as user <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent <br>
then as root <br>
sudo su <br>
cd /root <br>
mkdir .gnupg <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent<br><br>
see [gpg setup](https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0#bookmark=id.kotw1gextu63) <br><br>
## Pyinstaller <br>
This version can be built with pyinstaller with main.spec. if building the launcher script /usr/local/bin/recentchanges and polkit have to be changed. <br><br>
in /usr/local/bin/recentchanges change python3 "$app_install"/src/rntchanges.py to "$app_install"/main in the two areas <br><br>
then in /usr/local/recentchanges/scripts/rntchangesfunctions ln121 to "$app_install"/main and line below <br><br>
and<br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy   ln14 <br>
change to /usr/local/recentchanges/main <br><br>
or use pyinstaller version with changes made <br>
replace the following files from pyinstaller source: <br>
/usr/local/bin/recentchanges <br>
/usr/local/recentchanges/scripts/rntchangesfunctions <br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy <br><br>
PyInstaller<br>
https://github.com/dreadwrr/Linux-Pyinstaller <br>
to build a binary with all the packages and not needing any on the system <br><br>

the filter is setup for nemesis 25.04 <br>
porteus configured filter https://drive.google.com/file/d/11MjrAc4rgfH3GR1sFTUkf4WsV4amcBOy/view?usp=sharing <br>
picture for graphic https://i.imgur.com/UoL7CHQ.jpeg<br><br>
ui source file https://drive.google.com/file/d/1ndV65m31pbRN7oFnh1ut4z867GPm7rYr/view?usp=sharing<br>

<br>
Manual
https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0  
Porteus forums
https://forum.porteus.org/  <br><br>

![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>


