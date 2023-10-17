# TL;DR:
 * Install https://github.com/AUTOMATIC1111/stable-diffusion-webui on the machine with the beefcake GPU (backend)
   * add --listen and --api commandline args
 * Put (at least) hauntedmirror.py and haarcascade_frontalface_default.xml on the frontend machine (can be same as backend)
 * pip install -r requirements.txt to install frontend dependencies (or look in the file and install them manually)

# Overview
This runs a simple Haunted Mirror effect (see demo & description at https://tim.cexx.org/?p=1628) that shows visitors a spookier version of themselves using Stable Diffusion. Minimum hardware requirements are a PC with supported GPU, a Webcam and an LCD monitor.

For convenience, the effect can optionally be run via a separate *backend* machine (running the Stable Diffusion part via a beefy GPU) and a more lightweight *frontend* machine (running just the webcam and display) over a local network. The *frontend* can be a Raspberry Pi or other small SBC to avoid having a noisy desktop tethered to the display running the effect (possibly on a poorly-supervised front porch).

# stable-diffusion-webui setup
This is probably the most finicky part, so get it working first. See the https://github.com/AUTOMATIC1111/stable-diffusion-webui README for detailed instructions. A supported GPU with at least 4GB of RAM is recommended. 

In all cases, you will need to add the --api commandline argument. If you will be running a separate frontend over a network, the --listen parameter must be added too. If running under Windows, add these (plus any memory options or other needed tweaks) to the 'set COMMANDLINE_ARGS=' line in webui-user.bat.

It is recommended to run the browser-based UI at least once to choose an initial model (install more if desired) and make sure everything is working. The model 'dreamlikeDiffusion10_10' produced good results for me out-of-the-box.

If running Windows with a separate frontend, you may also need to tweak the Windows Firewall settings to make it connectable over the network. By default, the WebUI uses TCP port 7860 and this needs to be opened in the firewall for local clients. If you're very lucky, the first time you run it you'll be prompted to allow access over private (yes) and/or public (not recommended) networks. However, if you've previously made a different selection at this prompt, changed WebUI settings later, or Windows has decided to randomly reclassify your home Wifi as a public network (this happened to me), you will have to fix that or manaully fix the settings. See walkthrough at https://www.reddit.com/r/StableDiffusion/comments/xtkovu/is_there_a_way_i_can_share_my_local_automatic1111/ to manually unblock the port.

# Haunted Mirror frontend setup
## Installation
Ensure a recent Python 3 is installed and at least the hauntedmirror.py and haarcascade_frontalface_default.xml files are saved in a convenient location on disk. Install any required dependencies using:

pip install -r requirements.txt

Of course, if you are using Anaconda or another Python environment management scheme, follow the best practices of your chosen scheme. You can also just open requirements.txt in a text editor and install the dependencies manually (there are only a few). If installing on a Raspberry Pi, see special instructions below.

### Installation for Raspberry Pi 
This may work on a Pi 3+ "out of the box" with adequate performance (I haven't tested); on a Pi 2 "version 1.1" (ARM7) I tested with, frame acquisition was pretty laggy (several seconds behind) without workarounds.

When tested on Raspberry Pi OS "Oct 10 2023" version, I ran into some dependency issues. Ordinarily, the Raspberry Pi OS pulls Python packages from https://www.piwheels.org/, a repository of pre-compiled binary packages (wheels) to avoid glacially slow compilations on the lightweight hardware, but at the time of this writing, recent versions appear to be broken: no prebuilt wheels can be found, and install falls back to compiling from scratch, which fails with missing dependencies, e.g.:

FileNotFoundError: [Errno 2] No such file or directory: '_skbuild/linux-armv7l-3.9/cmake-install/python/cv2/config-3.py'

(This may, or may not, explain the missing wheels. Who knows.) For me, version 4.3.0.38 was the newest available with a valid wheel; this can be manually installed using:

pip install opencv-python==4.3.0.38

After this, you may get lucky with a newer version with binaries available, using:
pip install opencv-python --upgrade --prefer-binary 

Additionally, to get opencv working, several *binary* dependencies need to be installed (from your system package manager, not Python packages). If you receive the following errors when starting the script:

ImportError: libcblas.so.3: cannot open shared object file: No such file or directory  
libopenblas.so.0: cannot open shared object file: No such file or directory 

Try manually installing the packages *libatlas-base-dev* and *libopenblas-dev*:

sudo apt-get install libatlas-base-dev libopenblas-dev

## Setup
For now, all configuration options are just hardcoded at the top of the script; open it in any self-respecting (or at least whitespace-respecting) text editor, and adjust the items listed under *User Configurable Settings* as desired. There are several potentially mission-critical settings here, including the ip/port of the WebUI backend (if separate from the frontend or non-default port), serial port for the lighting effect (if used), and optional output directory for before/after images.

# Lighting effect setup
The lighting effect is optional, but adds to be *ambiance* and mainly helps paper over the delay waiting for the Stable Diffusion backend to do its thing. Requirements:

* Arduino-compatible microcontroller board with serial (or USB-serial) interface
* High-brightness LEDs and driver circuit

First, ensure the *Arduino* folder and its contents are somewhere accessible to the Arduino IDE. Open the project and you should have 'flicker' (flicker.ino) open in the IDE's editor window. As with the main script, user-configurable values are just global variables at the top. Here, adjust the I/O pin (must be a PWM-capable pin) you will use to control the driver, port baudrate (if using a physical port), and the max/min brightness values. When satisfied, upload to your board, ensure the LED/driver are physically connected and attach an external power supply (if needed). Connect the USB/serial port to your frontend machine and set up the resulting port in the hauntedmirror.py script.

## Simple Driver Circuit
This is not an electronics tutorial, but search the web for "NPN transistor LED driver" for a simple circuit example. For the super-short version:

Parallel

                    R1       D1   c Q1 e
    +V -+---------/\/\/\/----|>|---\_/---+
    +V  |---------/\/\/\/----|>|----|b   |
                    ...             |    |
    PWM --/\/\/\--------------------|    |
            R2                           |
    GND ---------------------------------+


Series

                    R1      D1   D2   D3      c Q1 e
    +V ----------/\/\/\/----|>|--|>|--|>|-...--\_/---+
    PWM --/\/\/\--------------------------------|b   |
            R2                                       |
    GND ---------------------------------------------+

* R1: Chosen to limit LED current to a safe value (check LED datasheet)
* R2: Base bias resistor (value not critical, in the range 330 ohm ~ 1K should be fine)
* Q1: NPN power transistor capable of handling total LED current & power (check transistor datasheet). Usual old suspects like TIP31A, 2N3055, etc. Consider a small heatsink if needed.