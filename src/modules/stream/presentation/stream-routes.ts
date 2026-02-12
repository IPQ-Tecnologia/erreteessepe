import path from 'path';

import type expressWs from 'express-ws';

import { ResolveCameraStreamUrl } from '../application/resolve-camera-stream-url';
import type { CameraRegistry } from '../domain/types';
import { buildStreamWebSocketHandler } from './stream-websocket-handler';

type RelayProxyFactory = Parameters<typeof buildStreamWebSocketHandler>[1];

interface StreamRouteDependencies {
  app: expressWs.Application;
  relayScriptUrl: string;
  relayProxy: RelayProxyFactory;
  cameraRegistry: CameraRegistry;
  resolveCameraStreamUrl: ResolveCameraStreamUrl;
}

const TEST_PAGE_PATH = path.resolve(process.cwd(), 'test.html');

export const registerStreamRoutes = ({
  app,
  relayScriptUrl,
  relayProxy,
  cameraRegistry,
  resolveCameraStreamUrl,
}: StreamRouteDependencies): void => {
  app.ws('/api/stream', buildStreamWebSocketHandler(resolveCameraStreamUrl, relayProxy));

  app.get('/api/cameras', (_request, response) => {
    response.status(200).json({ cameras: cameraRegistry.list() });
  });

  app.get('/jsmpeg.min.js', (_request, response) => {
    response.redirect(relayScriptUrl);
  });

  app.get('/', (_request, response) => {
    response.sendFile(TEST_PAGE_PATH);
  });
};
