from menu import Menu
import json
import Auxiliary

if __name__ == "__main__":

    #Define subject
    subject = "subject1"

    #Define data folder
    data_folder = f"data/{subject}/"

    media_folder = "gestures/"
    #What gestures to include
    gestures = [4, 6, 12]

    Auxiliary.download_gestures(gestures, media_folder, download_imgs=False)

    Menu(subject, data_folder, gestures, media_folder)