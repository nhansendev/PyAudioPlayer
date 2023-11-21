import os
import ffmpeg


def read_metadata(path):
    if not os.path.isfile(path):
        return "Unknown", None

    tag = ffmpeg.probe(path)["format"]["tags"]

    try:
        genre = tag["genre"]
    except KeyError:
        genre = "Unknown"

    try:
        year = tag["year"]
    except KeyError:
        year = None

    return [genre, year]


def check_normalized(path):
    tag = ffmpeg.probe(path)["format"]["tags"]

    if "Norm" in tag.keys():
        return tag["Norm"] == "True"
    else:
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
    out = ffmpeg.overwrite_output(out)
    ffmpeg.run(out, quiet=True)

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
    ffmpeg.run(out)

    os.replace(tmp_name, original_name)
