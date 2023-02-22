import os
import shutil

data_dir = "./vox2_crop_fps25/"
out_dir = "./vox2_crop_fps25_2/"
idx = 0
mode = 0
for i in os.listdir(data_dir):
    general_txt = i
    #if not os.path.exists(f"./vox2_crop_fps25_1/{general_txt}"):
        #os.makedirs(f"./vox2_crop_fps25_1/{general_txt}/")
    vid_fol = os.path.join(data_dir, i)

    vids = [os.path.join(vid_fol, v) for v in os.listdir(vid_fol)]
    vids = vids[: len(vids) // 12 * 12]
    idx = ((idx // 12)+1) * 12
    for v in vids:
        if idx % 12 == 0:
            os.makedirs(os.path.join(out_dir, f"{idx//12}"))
        if mode == 0:
            shutil.copy(v, os.path.join(out_dir, f"{idx//12}", str(idx) + '.png'))
        else:
            os.rename(v, os.path.join(out_dir, f"{idx//12}", str(idx) + '.png'))
        idx+=1