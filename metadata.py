# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import os
import ffmpeg
import mutagen


def read_metadata(path):
    if not os.path.isfile(path):
        return [0, "Unknown", None]

    try:
        file = mutagen.File(path)
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


if __name__ == "__main__":
    pass

    # import time
    # import mutagen

    # folder = "D:\\Songs"
    # songpath = "D:\\Songs\\3 Doors Down - Here Without You.mp3"

    # print(mutagen.File(songpath).info.length)

    # N = 100
    # st = time.time()
    # for _ in range(N):
    #     mutagen.File(songpath).keys()
    #     # read_metadata(songpath)
    # print(f"{(time.time()-st)/N:.3f} sec avg")

    # st = time.time()
    # for f in os.listdir(folder):
    #     read_metadata(f)
    # print(f"{time.time()-st:.3f} sec")
