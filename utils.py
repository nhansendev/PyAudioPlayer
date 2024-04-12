# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import os
import subprocess
from metadata import read_metadata, set_normalized
from pydub import AudioSegment, effects
from pydub.exceptions import CouldntDecodeError


def set_volume(val):
    # Linux
    subprocess.call(
        ["amixer", "-D", "pulse", "sset", "Master", f"{val}%"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def get_volume():
    # Linux
    var = subprocess.check_output(["amixer", "-D", "pulse", "sget", "Master"])
    var = str(var).split("Playback")[-1].split("[")[1].split("%")[0]
    try:
        return int(var)
    except ValueError:
        print("ERROR: Could not parse system volume!")
        return None


def sec_to_HMS(value, buffer=3):
    # Convert numerical seconds to string HH:MM:SS / MM:SS
    value = max(0, value)
    h = value / 3600
    m = 60 * (h - int(h))
    s = 60 * (m - int(m))
    if int(h) > 0:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
    else:
        return " " * buffer + f"{int(m):02d}:{int(s):02d}"


def _search_dir(filepath, extensions=[".mp3", ".wav"]):
    # Only grab files with the right extension(s)
    songs = os.listdir(filepath)
    temp = []
    for s in songs:
        for ext in extensions:
            if s.endswith(ext):
                temp.append(s)
                break
    return temp


def find_songs(filepath, extensions=[".mp3", ".wav"], printout=None):
    # Search a given directory for files with valid extensions
    # Then grab metadata from those files
    def _prnt(message):
        # For printing to a widget or terminal
        if printout is not None:
            printout(message)
        else:
            print(message)

    if not os.path.exists(filepath):
        _prnt("ERROR: Provided directory is not accessible!")
        return

    _prnt("Collecting songs and extracting metadata...")

    songs = _search_dir(filepath, extensions)

    if len(songs) == 0:
        _prnt(
            f"ERROR: No files with given extension(s) {extensions} found in directory!"
        )
        return

    # Sort by title using lowercase characters
    songs.sort(key=lambda x: x.lower())

    _prnt(f"Found {len(songs)} song(s)")

    out = []
    for song in songs:
        data = read_metadata(os.path.join(filepath, song))
        out.append([song, sec_to_HMS(data[0])] + data[1:])
    return out


def _norm(path):
    try:
        tmp = effects.normalize(AudioSegment.from_mp3(path))
    except CouldntDecodeError:
        return

    try:
        tmp.export(path, format="mp3", bitrate="128k")
        set_normalized(path, None, "True")
    except PermissionError:
        return


if __name__ == "__main__":
    pass

    # from metadata import check_normalized

    # path = "D:\\Songs\\Meh"
    # songs = os.listdir(path)
    # N = len(songs)

    # def check_norm():
    #     for s in songs:
    #         print(f"{check_normalized(os.path.join(path, s))}, {s}")

    # def clear_norm():
    #     for i, s in enumerate(songs):
    #         if i > 0 and i % (N // 10) == 0:
    #             print(f"{i+1}/{N} completed")
    #         set_normalized(path, s, False)
    #     print(f"{i+1}/{N} completed")

    # check_norm()
    # clear_norm()
