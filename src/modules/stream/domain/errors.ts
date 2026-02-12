export class CameraNotFoundError extends Error {
  public readonly cameraId: string;
  public readonly availableCameras: readonly string[];

  constructor(cameraId: string, availableCameras: readonly string[]) {
    super(`Unknown camera \"${cameraId}\"`);
    this.name = 'CameraNotFoundError';
    this.cameraId = cameraId;
    this.availableCameras = availableCameras;
  }
}
