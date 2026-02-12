export type CameraStreamMap = Readonly<Record<string, string>>;

export interface CameraRegistry {
  get(cameraId: string): string | undefined;
  list(): readonly string[];
}
