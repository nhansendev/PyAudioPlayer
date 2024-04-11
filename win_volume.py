# Copyright (c) 2023, Nathan Hansen
# All rights reserved.

# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

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
        # Rounding fixes a bug where the volume slider would slowly creep down over time.
        # Some kind of floor function in Windows created an inconsistent feedback loop.
        return round(self.volume.GetMasterVolumeLevelScalar() * 100, 0)

    def set_volume(self, value):
        value = min(1, max(0, value / 100))
        self.volume.SetMasterVolumeLevelScalar(value, None)
