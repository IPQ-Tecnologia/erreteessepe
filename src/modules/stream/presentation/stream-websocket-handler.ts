import type { Request } from 'express';
import type { WebSocket } from 'ws';

import { CameraNotFoundError } from '../domain/errors';
import { ResolveCameraStreamUrl } from '../application/resolve-camera-stream-url';
import { validateCameraConnection } from '../application/validate-camera-connection';

type RelayProxyHandler = (ws: WebSocket) => void;

type RelayProxyFactory = (params: {
  url: string;
  additionalFlags: string[];
  verbose: boolean;
  transport: 'tcp';
  useNativeFFmpeg: true;
}) => RelayProxyHandler;

const WS_CLOSE_CODES = {
  INVALID_REQUEST: 1008,    // Policy violation (invalid camera param)
  UNREACHABLE: 4001,        // camera unreachable
  AUTH_FAILED: 4003,        // authentication failed
  STREAM_ERROR: 4000,       // generic stream error
  INTERNAL_ERROR: 1011,     // internal error
} as const;

const MAX_CLOSE_REASON_LENGTH = 123;

const truncateReason = (reason: string): string =>
  reason.length <= MAX_CLOSE_REASON_LENGTH
    ? reason
    : reason.slice(0, MAX_CLOSE_REASON_LENGTH - 3) + '...';

const closeWithError = (
  ws: WebSocket,
  code: number,
  reason: string,
): void => {
  console.log(`Closing WebSocket with code ${code} and reason: ${truncateReason(reason)}`);
  ws.close(code, truncateReason(reason));
};

const parseCameraQuery = (request: Request): string | null => {
  const rawCamera = request.query.camera;

  if (Array.isArray(rawCamera)) {
    const firstCamera = rawCamera[0];
    return typeof firstCamera === 'string' && firstCamera.trim().length > 0
      ? firstCamera
      : null;
  }

  if (typeof rawCamera === 'string' && rawCamera.trim().length > 0) {
    return rawCamera;
  }

  return null;
};

export const buildStreamWebSocketHandler = (
  resolveCameraStreamUrl: ResolveCameraStreamUrl,
  relayProxy: RelayProxyFactory,
) => {
  return async (ws: WebSocket, request: Request): Promise<void> => {
    const cameraId = parseCameraQuery(request);

    if (!cameraId) {
      closeWithError(ws, WS_CLOSE_CODES.INVALID_REQUEST, 'invalid camera');
      return;
    }

    let streamUrl: string;

    try {
      streamUrl = resolveCameraStreamUrl.execute(cameraId);
    } catch (error) {
      if (error instanceof CameraNotFoundError) {
        closeWithError(ws, WS_CLOSE_CODES.INVALID_REQUEST, 'camera not found');
        return;
      }

      closeWithError(ws, WS_CLOSE_CODES.INTERNAL_ERROR, 'stream setup failed');
      return;
    }

    const connectionStatus = await validateCameraConnection(streamUrl);

    if (!connectionStatus.ok) {
      const codeMap = {
        unreachable: WS_CLOSE_CODES.UNREACHABLE,
        auth_failed: WS_CLOSE_CODES.AUTH_FAILED,
        stream_error: WS_CLOSE_CODES.STREAM_ERROR,
      } as const;

      console.log(`Camera connection validation failed for ${streamUrl}: ${connectionStatus.reason} - ${connectionStatus.message}`);

      closeWithError(ws, codeMap[connectionStatus.reason], connectionStatus.message);
      return;
    }

    relayProxy({
      url: streamUrl,
      additionalFlags: ['-q', '1'],
      verbose: true,
      transport: 'tcp',
      useNativeFFmpeg: true,
    })(ws);
  };
};
