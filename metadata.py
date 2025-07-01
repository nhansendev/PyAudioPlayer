# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import os
import ffmpeg
import mutagen
from mutagen.mp3 import MP3


def read_metadata(path):
    if not os.path.isfile(path):
        return [0, "Unknown", None]

    try:
        # file = mutagen.File(path)
        file = MP3(path)  # much faster
    except mutagen.mp3.HeaderNotFoundError:
        return [0, "Unknown", None]

    tags = file.tags
    duration = file.info.length

    genre = "Unknown"
    year = None
    for k in tags.keys():
        if "tcon" in k.lower():
            # TCON is an official, recognised tag representing genre
            genre = tags[k]

        if "year" in k.lower():
            # Year is not an official tag and is stored as TXXX:Year as a custom entry
            year = tags[k]

    return [duration, genre, year]


def check_normalized(path):
    try:
        tags = mutagen.File(path).tags
    except (mutagen.mp3.HeaderNotFoundError, FileNotFoundError):
        return False

    for k in tags.keys():
        if "norm" in k.lower():
            # State is stored as a string
            return tags[k] == "True"
    return False


def set_normalized(basepath, songname, state):
    if songname is None:
        original_name = basepath
    else:
        original_name = os.path.join(basepath, songname)
    tmp_name = original_name.split(".")
    tmp_name = ".".join([tmp_name[0] + "_TMP"] + tmp_name[1:])

    song = ffmpeg.input(original_name)
    out = ffmpeg.output(
        song,
        tmp_name,
        acodec="copy",
        metadata=f"Norm={state}",
    )

    ffmpeg.run(out, quiet=True, overwrite_output=True)

    os.replace(tmp_name, original_name)


def write_metadata(basepath, songname, genre, year):
    original_name = os.path.join(basepath, songname)
    tmp_name = original_name.split(".")
    tmp_name = ".".join([tmp_name[0] + "_TMP"] + tmp_name[1:])

    song = ffmpeg.input(original_name)
    out = ffmpeg.output(
        song,
        tmp_name,
        acodec="copy",
        **{
            "metadata": f"Year={year}",
            "metadata:": f"Genre={genre}",
        },
    )
    out = ffmpeg.overwrite_output(out)
    ffmpeg.run(out, quiet=True)

    os.replace(tmp_name, original_name)


def write_db_csv(folder, data):
    # Assume data in [name, duration, genre, year] format
    outstr = "\n".join([",".join([str(d) for d in entry]) for entry in data])
    with open(os.path.join(folder, "_meta_db.csv"), "bw") as f:
        f.write(outstr.encode())


def read_db_csv(folder):
    # Assume data in [name, duration, genre, year] format
    with open(os.path.join(folder, "_meta_db.csv"), "br") as f:
        lines = f.readlines()

    return [line.decode().strip().split(",") for line in lines]


if __name__ == "__main__":
    folder = "D:\\Songs\\Meh"
    read_db_csv(folder)

    # songs = os.listdir(folder)

    # song_data = []
    # for song in songs:
    #     tmp = read_metadata(os.path.join(folder, song))
    #     song_data.append([song] + tmp)

    # write_db_csv(folder, song_data)

    # slen = len(songs)
    # for i, s in enumerate(songs):
    #     if i % (slen // 10) == 0:
    #         print(f"Progress: {i+1}/{slen} ({(i+1)/slen:.1%})")
    #     set_normalized(folder, s, False)
