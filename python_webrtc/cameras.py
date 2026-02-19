import os

from .models import Camera

# todo: load from request or get from database
def load_cameras() -> dict[str, Camera]:
    cameras = {
        "dss": Camera(
            id="dss",
            name="DSS Playback",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_DSS_URL",
                "rtsp://192.168.202.165:9320/playback/center/110?streamID=224&beginTime=1745783566&endTime=1745784000",
            ),
        ),
        "cam1": Camera(
            id="cam1",
            name="Camera 1",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_CAM1_URL",
                "rtsp://admin:admin%40123@192.168.101.212:554/cam/realmonitor?channel=1&subtype=0",
            ),
        ),
        "cam2": Camera(
            id="cam2",
            name="Camera 2",
            rtsp_url=os.getenv(
                "RTSP_CAMERA_CAM2_URL",
                "rtsp://admin:admin123@192.168.101.211:554/cam/realmonitor?channel=1&subtype=0",
            ),
        ),
    }

    if not cameras:
        raise RuntimeError(
            "No cameras configured. Set RTSP_CAMERA_DSS_URL, RTSP_CAMERA_CAM1_URL, and RTSP_CAMERA_CAM2_URL."
        )

    return cameras
