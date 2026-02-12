import { CameraNotFoundError } from '../domain/errors';
import type { CameraRegistry } from '../domain/types';

export class ResolveCameraStreamUrl {
  constructor(private readonly cameraRegistry: CameraRegistry) {}

  execute(cameraId: string): string {
    const streamUrl = this.cameraRegistry.get(cameraId);

    if (!streamUrl) {
      throw new CameraNotFoundError(cameraId, this.cameraRegistry.list());
    }

    return streamUrl;
  }
}
