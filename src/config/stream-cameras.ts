import { env } from './env';
import type { CameraStreamMap } from '../modules/stream/domain/types';

const CAMERA_ENV_PREFIX = 'RTSP_CAMERA_';
const CAMERA_ENV_SUFFIX = '_URL';

type CameraEntry = readonly [cameraId: string, streamUrl: string];

const hasCameraKeyFormat = (key: string): boolean =>
  key.startsWith(CAMERA_ENV_PREFIX) &&
  key.endsWith(CAMERA_ENV_SUFFIX) &&
  key.length > CAMERA_ENV_PREFIX.length + CAMERA_ENV_SUFFIX.length;

const buildCameraEntry = (envKey: string): CameraEntry | null => {
  const rawCameraId = envKey
    .slice(CAMERA_ENV_PREFIX.length, -CAMERA_ENV_SUFFIX.length)
    .trim();
  const streamUrl = env.optionalString(envKey);

  if (!rawCameraId || !streamUrl) {
    return null;
  }

  return [rawCameraId.toUpperCase(), streamUrl];
};

const cameraEntries = Object.keys(process.env)
  .filter(hasCameraKeyFormat)
  .map(buildCameraEntry)
  .filter((entry): entry is CameraEntry => entry !== null);

if (cameraEntries.length === 0) {
  throw new Error(
    'No RTSP cameras configured. Define at least one environment variable in the form RTSP_CAMERA_<ID>_URL.',
  );
}

export const STREAM_CAMERAS: CameraStreamMap = Object.freeze(
  Object.fromEntries(cameraEntries),
);
