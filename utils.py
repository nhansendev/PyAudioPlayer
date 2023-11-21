import os
import subprocess
from metadata import read_metadata, check_normalized, set_normalized
from multiprocessing import get_context, Pool
from ffmpeg import probe
from pydub import AudioSegment, effects
from tqdm import tqdm


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

    return _parallel_read_metadata(songs, filepath)


def _get_metadata(basepath, song):
    path = os.path.join(basepath, song)
    dur = sec_to_HMS(float(probe(path)["format"]["duration"]))
    return [song, dur] + read_metadata(path)


def _parallel_read_metadata(song_set, filepath):
    # Using spawn for compatability between Unix and Windows
    with get_context("spawn").Pool() as p:
        temp = p.starmap(
            _get_metadata,
            list(zip(*[[filepath] * len(song_set), song_set])),
        )

    return temp


def _norm(path):
    tmp = effects.normalize(AudioSegment.from_mp3(path))
    tmp.export(path, format="mp3", bitrate="128k")

    set_normalized(path, None, "True")


def volume_normalizer(basepath, songs=None):
    if songs is None:
        songs = _search_dir(basepath)
    print(f"Checking {len(songs)} file(s)...")
    to_convert = []
    for s in songs:
        path = os.path.join(basepath, s)
        if not check_normalized(path):
            to_convert.append(path)

    if len(to_convert) > 0:
        print("Processing...")
        with Pool() as p:
            with tqdm(total=len(to_convert)) as TQ:
                for _ in p.imap_unordered(_norm, to_convert):
                    TQ.update()

        print(f"Done, normalized: {len(to_convert)} files")
    else:
        print("Nothing found to normalize.")


if __name__ == "__main__":
    basedir = "D:\\Songs"
    volume_normalizer(basedir)
