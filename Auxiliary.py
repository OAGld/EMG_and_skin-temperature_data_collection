import os
from os import walk
import json

def download_gestures(gesture_ids, folder, download_imgs=True, download_gifs=False, redownload=False):
    """
    Downloads gesture images (either .png or .gif) from: 
    https://github.com/libemg/LibEMGGestures.
    
    This function dowloads gestures using the "curl" command. 

    Parameters
    ----------
    gesture_ids: list
        A list of indexes corresponding to the gestures you want to download. A list of indexes and their respective 
        gesture can be found at https://github.com/libemg/LibEMGGestures.
    folder: string
        The output folder where the downloaded gestures will be saved.
    download_gif: bool (optional), default=False
        If True, the assocaited GIF will be downloaded.
    redownload: bool (optional), default=False
        If True, all files will be re-downloaded (regardless if they are already downloaed).
    """
    git_url = "https://raw.githubusercontent.com/libemg/LibEMGGestures/main/"
    gif_folder = "GIFs/"
    img_folder = "Images/"
    json_file = "gesture_list.json"
    curl_commands = "curl --create-dirs" + " -O --output-dir " + folder + " "

    files = next(walk(folder), (None, None, []))[2]

    # Check JSON file exists
    if not json_file in files or redownload:
        os.system(curl_commands + git_url + json_file)

    json_file = json.load(open(folder + json_file))

    for id in gesture_ids:
        idx = str(id)
        img_file = json_file[idx] + ".png"
        gif_file = json_file[idx] + ".gif"
        if download_imgs and (not img_file in files or redownload):
            os.system(curl_commands + git_url + img_folder + img_file)
        if download_gifs:
            if not gif_file in files or redownload:
                os.system(curl_commands + git_url + gif_folder + gif_file)