'''
Haunted Mirror script: This uses a webcam, "magic mirror" (2-way glass over a monitor) and the AUTOMATIC1111 StableDiffusion
web UI (https://github.com/AUTOMATIC1111/stable-diffusion-webui) to detect viewers looking into the mirror and replace
their reflection with a spookier version. Optionally, control a lighting source to enhance the haunted effect.

Crib sources:
https://realpython.com/face-detection-in-python-using-a-webcam/
https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/12083

By Tim (drmn4ea at google's mail)

Requirements:
StableDiffusion WebUi (https://github.com/AUTOMATIC1111/stable-diffusion-webui)
Python-opencv (cv2)
NumPy

'''
import json
import base64
import requests
import os
import os.path
import errno
import sys
import traceback
import cv2
import numpy as np
import serial
#from tqdm import tqdm
import time

#########   User Configurable Settings #################

stdip = 'http://127.0.0.1:7860' # Default running on localhost
lighting_com_port = 'COM1' # Default com port for lighting control, or None if not used (ex: 'COM1', '/dev/ttyACM0', etc.)
image_output_path = None # Output directory for before/after images (e.g. './output'); leave as None to skip saving images. Use forward slash for path separator (even Windoze)
img_height = 512 # Image width for SD output; most models are trained on 512x512 or 512x768 and may produce odd results at other sizes
img_width = 768 # You can tweak the aspect ratio to better match your display if needed, or just cover any letterbox bars with black paper :-)
img_reverse = True # Undo horizontal mirroring between the webcam and viewer. If image seems reversed (subjects at left left in the mirror are at right on the screen), try disabling this
vert_comp = 0.0 # 0.0 ~ 1.0. Assuming webcam is mounted at top of screen, 0.5 to crop/shift image up 1/2 screen to more closely match mirror (appear centered).
timeout_sec = 10.0 # Timeout when waiting for StableDiffusion results
frame_grab_delay_sec = 1.5 # Delay between first face detect frame and frame grab; gives a little more time for victim to fully enter the frame
display_time = 2.5 # Duration in seconds to display the spookified image
# Settings for low-end frontend hardware
frame_skip_delay = 0.1 # Default delay to catch-up image frames to realtime on resource-constrained hardware (tested with RPi2)
display_breath_delay = 0.2  # on some platforms, imshow() seems to need some 'breathing time' in the form of a cv2.waitKey(...) with a minimum delay for the image to show/scale properly.
                            # If this delay is set too low, fullscreen windows do not get scaled properly.

# Stable Diffusion key settings, see get_sd_image() below for some minor ones
sd_denoising_strength = 0.45 # Range 0-1, smaller value closer to original image. 0.45 is a good starting point.
sd_num_steps = 9 # Number of iterations (speed vs. quality tradeoff, more is better/slower).
sd_cfg_scale = 12 # Weighting of text prompt (higher=more), rage ~0-30, sweet spot of ~5-15.
sd_prompt = "spooky scary skeletons" # Text prompt, generic Halloweeny terms seem to work well

#########   End User Configurable Settings #################

def submit_post(url: str, data: dict):
    return requests.post(url, data=json.dumps(data), timeout=timeout_sec)

def image_to_base64(image):
    encoded_string = base64.b64encode(image)
    base64_string = encoded_string.decode("utf-8")
    return base64_string

def save_image(decoded_image, output_path):
    print ("Saving, output path: %s, Image payload len: %u" % (output_path, len(decoded_image)))
    # Check if file exists, create if it doesn't exist
    dirs, fname = output_path.rsplit('/', 1)
    # Taken from https://stackoverflow.com/a/600612/119527
    try:
        os.makedirs(dirs)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(dirs):
            pass
        else:
            raise

    if not os.path.exists(output_path):
        open(output_path, 'wb').close()

    # Open file in binary mode     
    with open(output_path, 'wb') as f:
        f.write(decoded_image)
        f.flush()
        f.close()

def crop_cv_img(img, xmin, xmax, ymin, ymax):
    ''' Normalized crop (0 to 1) '''

    [myheight, mywidth, colors] = img.shape
    if xmax<=1 and ymax <= 1:
        # Normalized crop
        print (img.shape)
        print (xmax)
        xmin = int(xmin * mywidth)
        ymin = int(ymin * myheight)
        xmax = int(xmax * mywidth)
        ymax = int(ymax * myheight)
        print(xmax, ymax)
        ret = img[ymin:ymax, xmin:xmax, :]
        print("Outgoing shape")
        print (ret.shape)
    return ret

def frame_eating_delay(vidcap, t):
    '''
    Delay while consuming image frames.
    vidcap: OpenCV VideoCapture object
    t: time to delay, in seconds or fractions thereof
    '''

    deadline = time.time() + t
    while time.time() < deadline:
        vidcap.read() # ignore the result

def webcam_face_detect(video_mode, displaytime=2.0, cascasdepath="haarcascade_frontalface_default.xml", comport=None):

    face_cascade = cv2.CascadeClassifier(cascasdepath)

    video_capture = cv2.VideoCapture(video_mode)
    num_faces = 0

    # Window to test webcam output and face detection
    cv2.namedWindow("Faces",  cv2.WINDOW_NORMAL)
    #cv2.setWindowProperty("Faces", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Window for actual spookification results, fullscreen
    cv2.namedWindow("Spookified",  cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Spookified", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Create a black image frame the same size as the expected SD output.
    # This will allow for clearing the screen between outputs.
    # TODO: Fix aspect ratio issues / letterbox bars

    all_black_frame = np.zeros((img_height, img_width, 3))
    cv2.imshow("Spookified", all_black_frame)

    # Window and its content (imshow...) seems to be only displayed during a 'waitKey'.
    # Open some combination of (Linux/X11/resource-limited hardware) OpenCV port seems to require this specific
    # type of delay (not Python sleep, etc.) in order to properly spawn and scale the window.
    cv2.waitKey(int(display_breath_delay*1000))

    # Set up initial lighting state, if used
    if comport:
        comport.write(b'L') # Lit

    while True:
        # If so configured, delay a bit to consume old image frames as quickly as possible (ideally catch back up to realtime).
        # This can prevent image frames lagging some seconds behind reality on lower-end hardware.
        frame_eating_delay(video_capture, frame_skip_delay)

        ret, image_frame = video_capture.read()

        if not ret:
            print("Failed grabbing image frame")
            break

        image_frame = crop_cv_img(image_frame,0,1,vert_comp,1)

        # Cascade classifier expects a grayscale image
        gray = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)

        # User Haar cascade classifier to detect faces. This is not the latest-n-greatest, but works well enough
        # and should run in realtime even on resource-limited hardware (aggregate-fruit-inspired SBCs or otherwise).
        # Save your GPU for the actual spookification.
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor = 1.2,
            minNeighbors = 5,
            minSize = (30,30)
            )

        num_faces = len(faces)
        print("Faces found = ", num_faces)

        # Explicitly copy the webcam frame for debug output (show face detections)
        detection_image_frame = image_frame.copy()
        # draw bounding box for display
        for (x,y,w,h) in faces:
            cv2.rectangle(detection_image_frame, (x,y), (x+h, y+h), (0, 255, 0), 2)
        cv2.imshow("Faces", detection_image_frame)

        # If face(s) detected (someone's at the mirror), kick this frame off to StableDiffusion and grab the result.
        # This is simple and just blocks until the result is ready.
        if num_faces > 0:
            # Delay a bit and capture a frame for realsies. In my initial testing no delay would catch someone just walking into frame
            # or turned side-on, this optionally gives a bit more time for them to be in position. Pretty crude, but better than nothing.
            frame_eating_delay(video_capture, frame_grab_delay_sec)

            ret, image_frame = video_capture.read()

            if not ret:
                print("Failed grabbing image frame")
                break

            if img_reverse:
                # In the mirror, you're looking forward at you, but the webcam is flipped around 180 and looking back at you,
                # so the image is mirrored (unless they already correct for this; unlikely).
                image_frame = cv2.flip(image_frame, 1)

            image_frame = crop_cv_img(image_frame, 0, 1, vert_comp, 1)


            # Start lighting flicker effect here.
            # Generating the SD image takes a bit, so the idea of this is to visually show something is happening,
            # keep the viewer's eye drawn toward the mirror until the result is ready, and finally dim the lights
            # to help the display image show through. Plus, no haunting is complete without flickery lights.
            if comport:
                comport.write(b'F')  # Flicker

            # Python OpenCV works with images as NumPy arrays, and in BGR color order.
            # Convert the clean copy of the webcam frame to a memory buffer in a format the StableDiffusion backend can understand.
            retval, usable_image_frame = cv2.imencode('.png', image_frame)

            # submit the request
            sd_img = get_sd_image(usable_image_frame, img_size=[img_height,img_width])

            # TODO: Saving throw (static jumpscare image?) if SD backend times out

            if sd_img:
                if image_output_path: # Save a before/after copy?
                    # Cheesy unique filenames; we don't expect anyone to generate images faster than 100msec
                    base_filename = image_output_path + '/' + str(int(time.time()*10))
                    save_image(usable_image_frame, base_filename + '_orig.png')
                    save_image(sd_img, base_filename + '_spooky.png')

                # Translate incoming format (.png) back to something CV understands
                cv_sd_img = np.frombuffer(sd_img, dtype='uint8') # convert to NumPy array of the png
                cv_sd_img = cv2.imdecode(cv_sd_img, cv2.IMREAD_UNCHANGED) # convert to raw in BGR color order for display by OpenCV

                # Black out the vanity lighting so the 2-way mirror effect shows through
                if comport:
                    comport.write(b'D')  # Dark

                # Update display with spooky image
                cv2.imshow("Spookified", cv_sd_img)

                # Delay to show the result
                # Press q to quit (may take a few seconds)


                # Display in 2 parts. The first seems to give the rendering thread time to post/scale the image to its window properly
                # (if too low, 'fullscreen' image is squished into the top-left corner).
                # The second implements the bulk of the user-set delay without allowing camera frames to stack up
                if cv2.waitKey(int(display_breath_delay*1000)) & 0xFF == ord('q'):
                    break

                frame_eating_delay(video_capture, displaytime - display_breath_delay)

                # Restore black screen
                cv2.imshow("Spookified", all_black_frame)

                # Restore lighting to normal
                if comport:
                    comport.write(b'L')  # Lit

        # Press q to quit (may take a few seconds)
        if cv2.waitKey(int(display_breath_delay*1000)) & 0xFF == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()
    return num_faces

def get_sd_image(orig_image, img_size=[512, 768]):
    '''Given a source image buffer in a compatible format (.png/.jpg/etc.), call StableDiffusion backend using the parameters specified below
    and return the resulting image.
    '''

    # Path to automatic1111 webui's img2img API endpoint.
    # Must add "--api" to its commandline arguments to expose it.
    # (Windows: see "set COMMANDLINE_ARGS=" line in webui\webui-user.bat)
    img2img_url = stdip + '/sdapi/v1/img2img'

    if len(orig_image):
        # Set of parameters (json) passed to the API. Many can be omitted and the default will be used.
        # Hit the builtin documentation (e.g. http://127.0.0.1:7860/docs#/default/img2imgapi_sdapi_v1_img2img_post) for a list of recognized parameters
        data = {
            "init_images": [image_to_base64(orig_image)],  # Original image, must be a supported image format (.png, .jpg...) and base64 encoded
            "denoising_strength": sd_denoising_strength,
            # Range 0-1, smaller value closer to original image. Larger value more likely to let imagination fly
            # For output recognizably true to the source material, 0.45 seems to be a good starting point.
            "prompt": sd_prompt,  # Generic Halloweeny words like creepy, spooky, ghost, skeleton, graveyard, etc. seem to work well.
            # We don't know how many subjects will be in frame, their poses, costumes etc., and these models tend to be extensively trained on faces,
            # so being vague tends to work well at modifying faces without messing up other details.
            # Being overly specific tends to produce poorer results.
            #"negative_prompt": "ugly, tiling, poorly drawn hands, poorly drawn feet, poorly drawn face, out of frame, extra limbs, disfigured, deformed, body out of frame, blurry, bad anatomy, blurred, watermark, grainy, signature, cut off, draft",
            # Prompts SD what you *don't* want in the image. Of course, most of those things will just add to the spooky factor, so you may be better off leaving this blank unless your model requires it.
            # "styles": [],
            "seed": -1,
            # Initial seed. I feel images with the same seed are similar but not identical. -1 is random
            "steps": sd_num_steps,
            # Number of steps, more is generally better but slower (adjust for quality vs. response time tradeoff). Max 150 in webui, maybe can go higher here?
            "cfg_scale": sd_cfg_scale,  # Influence of prompt text on image, usually 5-15, max 30 in webui, can fine tune
            "width": img_size[1],  # Width
            "height": img_size[0],  # Height
            # Most models are trained on 512x512 and 512x768 images, so target one of those sizes for best results. See resize_mode below for how the incoming image is massaged to this size.
            "restore_faces": False,
            # Whether to correct faces. This adds a speed and GPU RAM penalty, and again, uncanny faces are kind of what we want, so leaving this off.
            "script_args": [],  # Parameters I haven't tried, keep this empty list
            "sampler_index": "DPM++ 2M Karras",
            # Sampling method, recommend DPM++ 2M Karras, good quality and fast. Can fine tune
            "resize_mode": 2,
            # Resize mode, 0: stretch, 1: crop (recommended), 2: pad, 3: scale (upsample latent)
            # "override_settings": {"sd_model_checkpoint": "your_model.safetensors",},
            # "hypernetwork_model": ["dic_demosaicing.pt"],
            # "script_args": [0,True,True,"hypernetwork_model","dic_demosaicing.pt",1,1],
            "sd_vae": "Automatic"
        }

        try:
            response = submit_post(img2img_url, data)
            print("Backend response: %s" % response)
            # for debugging, show the actual JSON response if any
            #print(response.json())
            b64_image = response.json()['images'][0]
        except Exception as ex:
            # Issue talking to backend (probably timeout). The show must go on, so fail as benignly as possible and try again next time
            print("SD image retrieval failed")
            print(traceback.format_exc())
            return None

        #print ("Response image payload len: %u" % len(b64_image))
        if len(b64_image):
            # Image is returned as a base64-encoded .png, decode it before passing back
            return base64.b64decode(b64_image)
        return None



if __name__ == "__main__":
    if len(sys.argv) < 2:
        video_mode= 0
    else:
        video_mode = sys.argv[1]
    if lighting_com_port is not None:
        comport = serial.Serial(lighting_com_port, 115200)
    else:
        comport = None
    webcam_face_detect(video_mode, displaytime=display_time, comport=comport)



