import type { CameraRegistry, CameraStreamMap } from '../domain/types';

export class InMemoryCameraRegistry implements CameraRegistry {
  constructor(private readonly cameras: CameraStreamMap) {}

  get(cameraId: string): string | undefined {
    return this.cameras[cameraId];
  }

  list(): readonly string[] {
    return Object.keys(this.cameras);
  }
}
