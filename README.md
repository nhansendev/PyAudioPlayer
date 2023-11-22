# PyAudioPlayer
An audio player GUI with yt_dlp integration, made in python using PySide6.

![AP_linux](https://github.com/nhansendev/PyAudioPlayer/assets/9289200/c632a38c-6c31-41a6-9f70-f541480fdd0c)

# Placeholder; much cleaning to do first! 🧹

# Requirements
## System
- Python 3.11
- Windows or Linux
## Packages 
>pip install -r requirements.txt

# Usage
Can be launched via terminal, or a shortcut pre-configured for the desired folder:

## Terminal
`> <parent folder path>\PyAudioPlayer\AudioPlayer.pyw <music folder path>`

## Shortcut (Windows)
Target: `<parent folder path>\PyAudioPlayer\AudioPlayer.pyw <music folder path>`

Start In: `<parent folder path>`

![image](https://github.com/nhansendev/PyAudioPlayer/assets/9289200/e8d3331d-5106-400b-b55b-207ef20fd7f0)

By default any .mp3 and .wav files in the music folder will be loaded.

# Utilities
## Volume Normalization
This utility uses the normalize effect from [pydub](https://github.com/jiaaro/pydub/blob/master/API.markdown) to target a more uniform volume across audio files.
Once a file has been normalize a tag is added to its metadata ("Norm=True"), which allows it to be ignored in the future.

### Terminal
`>python .\PyAudioPlayer\utils.py <music folder path>`

Ex: 3 files were already normalized of 16 total

    Checking 16 file(s)...
    Processing...
    100%|████████████████████████████████████████████████| 13/13 [00:22<00:00,  1.70it/s]
    Done, normalized: 13 files

### In Python
    from utils import volume_normalizer
  
    volume_normalizer(<music folder path>, <optional list of specific songs>)
