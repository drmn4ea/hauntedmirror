'''
Haunted Mirror script: This uses a webcam, "magic mirror" (2-way glass over a monitor) and the AUTOMATIC1111 StableDiffusion
web UI (https://github.com/AUTOMATIC1111/stable-diffusion-webui) to detect viewers looking into the mirror and replace
their reflection with a spookier version. Optionally, control a lighting source to enhance the haunted effect.

Crib sources:
https://realpython.com/face-detection-in-python-using-a-webcam/
https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/12083

By Tim (drmn4ea at google's mail)

'''
import json
import base64
import requests
import os

import sys
import cv2
import numpy as np
from tqdm import tqdm
import time

stdip = 'http://127.0.0.1:7860' # Default running on localhost
image_output_path = 'D:/stablediffusion/hallo/output' # Output directory for before/after images; leave blank to skip saving images

def submit_post(url: str, data: dict):
    return requests.post(url, data=json.dumps(data), timeout=10)

def image_to_base64(image):
    encoded_string = base64.b64encode(image)
    base64_string = encoded_string.decode("utf-8")
    return base64_string

def save_image(decoded_image, output_path):
    print ("Saving, output path: %s, Image payload len: %u" % (output_path, len(decoded_image)))
    # Check if file exists, create if it doesn't exist
    if not os.path.exists(output_path):
        open(output_path, 'wb').close()

    # Open file in binary mode     
    with open(output_path, 'wb') as f:
        f.write(decoded_image)
        f.flush()
        f.close()



def webcam_face_detect(video_mode, displaytime=2.0, cascasdepath = "haarcascade_frontalface_default.xml"):

    face_cascade = cv2.CascadeClassifier(cascasdepath)

    video_capture = cv2.VideoCapture(video_mode)
    num_faces = 0

    # Window to test webcam output and face detection
    cv2.namedWindow("Faces",  cv2.WINDOW_NORMAL)
    #cv2.setWindowProperty("Faces", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Window for actual spookification results, fullscreen
    cv2.namedWindow("Spookified",  cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Spookified", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while True:
        ret, image_frame = video_capture.read()

        if not ret:
            print("Failed grabbing image frame")
            break

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
            # TODO: Start lighting effect here (flicker the user-facing / vanity light source).
            # Generating the SD image takes a bit, so the idea of this is to visually show something is happening,
            # keep the viewer's eye drawn toward the mirror until the result is ready, and finally dim the lights
            # to help the display image show through. Plus, no haunting is complete without flickery lights.

            # Python OpenCV works with images as NumPy arrays, and in BGR color order.
            # Convert the clean copy of the webcam frame to a memory buffer in a format the StableDiffusion backend can understand.
            retval, usable_image_frame = cv2.imencode('.png', image_frame)

            # submit the request
            sd_img = get_sd_image(usable_image_frame)

            # TODO: Saving throw (static jumpscare image?) if SD backend times out

            if sd_img:
                if image_output_path: # Save a before/after copy?
                    base_filename = image_output_path + '/' + str(int(time.time()*10))
                    save_image(usable_image_frame, base_filename + '_orig.png')
                    save_image(sd_img, base_filename + '_spooky.png')

                # TODO: Cut/dim the vanity lights for screen display

                # Translate incoming format (.png) back to something CV understands
                cv_sd_img = np.frombuffer(sd_img, dtype='uint8') # convert to NumPy array of the png
                cv_sd_img = cv2.imdecode(cv_sd_img, cv2.IMREAD_UNCHANGED) # convert to raw in BGR color order for display by OpenCV
                #
                cv2.imshow("Spookified", cv_sd_img)
                time.sleep(displaytime)

                # TODO: Restore lighting to normal

        # Press q to quit (may take a few seconds)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()
    return num_faces

def get_sd_image(orig_image, file_name = None):
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
            "denoising_strength": 0.45,
            # Range 0-1, smaller value closer to original image. Larger value more likely to let imagination fly
            # For output recognizably true to the source material, 0.45 seems to be a good starting point.
            "prompt": "spooky scary skeletons",  # Generic Halloweeny words like creepy, spooky, ghost, skeleton, graveyard, etc. seem to work well.
            # We don't know how many subjects will be in frame, their poses, costumes etc., and these models tend to be extensively trained on faces,
            # so being vague tends to work well at modifying faces without messing up other details.
            # Being overly specific tends to produce poorer results.
            #"negative_prompt": "ugly, tiling, poorly drawn hands, poorly drawn feet, poorly drawn face, out of frame, extra limbs, disfigured, deformed, body out of frame, blurry, bad anatomy, blurred, watermark, grainy, signature, cut off, draft",
            # Prompts SD what you *don't* want in the image. Of course, most of those things will just add to the spooky factor, so you may be better off leaving this blank unless your model requires it.
            # "styles": [],
            "seed": -1,
            # Initial seed. I feel images with the same seed are similar but not identical. -1 is random
            "steps": 9,
            # Number of steps, more is generally better but slower (adjust for quality vs. response time tradeoff). Max 150 in webui, maybe can go higher here?
            "cfg_scale": 12,  # Influence of prompt text on image, usually 5-15, max 30 in webui, can fine tune
            "width": 768,  # Width
            "height": 512,  # Height
            # Most models are trained on 512x512 and 512x768 images, so target one of those sizes for best results. See resize_mode below for how the incoming image is massaged to this size.
            "restore_faces": False,
            # Whether to correct faces. This adds a speed and GPU RAM penalty, and again, uncanny faces are kind of what we want, so leaving this off.
            "tiling": False,  # Tiling, meaning left and right edges match, top and bottom match. Usually False
            "script_args": [],  # Parameters I haven't tried, keep this empty list
            "sampler_index": "DPM++ 2M Karras",
            # Sampling method, recommend DPM++ 2M Karras, good quality and fast. Can fine tune
            "resize_mode": 2,
            # Resize mode, 0: stretch, 1: crop, 2: pad, 3: scale (upsample latent), recommend crop, don't know which one 1 refers to here, can reselect later
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
        except:
            # Issue talking to backend (probably timeout). The show must go on, so fail as benignly as possible and try again next time
            print("SD image retrieval failed")
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
    webcam_face_detect(video_mode)



