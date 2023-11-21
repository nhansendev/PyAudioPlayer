from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume


class volume_controller:
    def __init__(self):
        # Windows
        # Get default audio device using PyCAW
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))

    def get_volume(self):
        return self.volume.GetMasterVolumeLevelScalar() * 100

    def set_volume(self, value):
        value = min(1, max(0, value / 100))
        self.volume.SetMasterVolumeLevelScalar(value, None)
