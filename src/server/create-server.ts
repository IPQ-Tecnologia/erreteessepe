import express from 'express';
import expressWs from 'express-ws';
import rtspRelay from 'rtsp-relay';

import { STREAM_CAMERAS } from '../config/stream-cameras';
import { ResolveCameraStreamUrl } from '../modules/stream/application/resolve-camera-stream-url';
import { InMemoryCameraRegistry } from '../modules/stream/infrastructure/in-memory-camera-registry';
import { registerStreamRoutes } from '../modules/stream/presentation/stream-routes';

export const createServer = (): expressWs.Application => {
  const expressApplication = express();
  const { app } = expressWs(expressApplication as never);
  const { proxy, scriptUrl } = rtspRelay(app as unknown as express.Application);

  const cameraRegistry = new InMemoryCameraRegistry(STREAM_CAMERAS);
  const resolveCameraStreamUrl = new ResolveCameraStreamUrl(cameraRegistry);

  registerStreamRoutes({
    app,
    relayScriptUrl: scriptUrl,
    relayProxy: proxy,
    cameraRegistry,
    resolveCameraStreamUrl,
  });

  return app;
};
