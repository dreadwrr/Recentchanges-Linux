New release! added changes and new features from windows version <br><br>
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
optionally can install the required packages in system using package manager<br><br>
If cant find command recentchanges move /usr/local/bin/recentchanges somewhere in path ie for porteus needs to be in /opt/porteus-scripts/ <br>
or make a symlink to /usr/local/bin . ln -s /usr/local/bin/recentchanges /usr/bin/recentchanges <br><br><br>

gpg setup <br>
as user <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent
then as root <br>
sudo su <br>
cd /root <br>
mkdir .gnupg <br>
echo "pinentry-program /usr/bin/pinentry-curses" > ~/.gnupg/gpg-agent.conf <br>
gpgconf --kill gpg-agent<br><br>
This version can be built with pyinstaller with main.spec. if building the launcher script /usr/local/bin/recentchanges and polkit have to be changed. <br><br>
in /usr/local/bin/recentchanges change python3 "$app_install"/src/rntchanges.py to "$app_install"/main in two places <br>
/usr/local/recentchanges/scripts/rntchangesfunctions ln121 to "$app_install"/main and line below <br><br>
and<br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy   ln14 <br>
change to /usr/local/recentchanges/main <br><br>
or use pyinstaller version with changes made <br>
replace the following files from pyinstaller source: <br>
/usr/local/bin/recentchanges <br>
/usr/local/recentchanges/src/rntchangesfunctions <br>
/usr/share/polkit-1/actions/org.freedesktop.set-recentchanges.policy <br><br>
PyInstaller<br>
https://github.com/dreadwrr/Linux-Pyinstaller <br>
to build a binary with all the packages and not needing any on the system <br><br>
picture for graphic https://i.imgur.com/UoL7CHQ.jpeg<br>

<br>
Manual
https://docs.google.com/document/d/1EJAKd1v41LTLN74eXHf5N_BdvGYlfU5Ai8oWBDSGeho/edit?tab=t.0  
Porteus forums
https://forum.porteus.org/  <br><br>

![Alt text](https://i.imgur.com/4jOp3Ry.png) ![Alt text](https://i.imgur.com/T1DpcDM.png) <br><br>


