from menu import Menu
import Auxiliary

if __name__ == "__main__":

    #Define subject
    subject = "subject1"

    #Define data folder
    data_folder = f"data/{subject}/"

    media_folder = "gestures/"
    #What gestures to include
    gestures = [1,2,3]

    sgt_args={
        'media_folder': media_folder,
        'data_folder':data_folder,
        'num_reps': 1, 
        'rep_time': 5, 
        'rest_time': 3, 
        'auto_advance': True, 
        'discrete': False
    }

    Auxiliary.download_gestures(gestures, media_folder, download_imgs=True)

    Menu(subject, data_folder, gestures, media_folder, sgt_args)