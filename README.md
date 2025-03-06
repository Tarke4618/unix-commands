# move-files
The unix script to move all files from source folder to destination folder by scaning it 5 layers deep and also deleting the empty folders in the source folder and also deleting any files other that images and GIFS the the destination folder


The file [1](move_files.sh) just move the files from source to destination with scanning 2 layers deep

The file [2](move&delete.sh) moves the files like the previous one but it also does delete the empty folders in the source folder

The file [3](move&delete&images.sh) moves the files from the source to the destination and also deletes the empty folders in the source and it also deletes the non-image files from the destination folder (everything except images and GIFs)

The final file (move_photos.sh) does all that but better example does that with any source or destination you want because it prompts you to select the folders instead of the previous ones which has a fixed source and destination.