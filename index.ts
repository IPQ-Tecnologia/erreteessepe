import express from 'express';
import expressWs from 'express-ws';
import rtspRelay from 'rtsp-relay';

const expressApp = express();

const {app} = expressWs(expressApp as never);

const { proxy, scriptUrl } = rtspRelay(app as unknown as express.Application);
const PORT = 1523;

const cams: Record<string, string> = {
  DSS: `rtsp://192.168.202.165:9320/playback/center/110?streamID=224&beginTime=1745783566&endTime=1745784000`,
  CAM1: `rtsp://admin:admin%40123@192.168.101.212:554/cam/realmonitor?channel=1&subtype=0`,
  CAM2: `rtsp://admin:admin123@192.168.101.211:554/cam/realmonitor?channel=1&subtype=0`,
}

// Endpoint que o frontend vai chamar para pegar o stream
app.ws('/api/stream', (ws, req) => {
  const { camera = 'none' } = req.query as { camera: string };

  if (!(camera in cams)) {
    console.log('Entrei aqui');
    ws.close(ws.CLOSED);
    // ws.on('message', (message) => ws.close(ws.CLOSED));
  }
  return proxy({
    url: cams[camera],
    additionalFlags: ['-q', '1'],
    verbose: true,
    transport: 'tcp',
    useNativeFFmpeg: true
  })(ws);
});

app.get('/jsmpeg.min.js', (req, res) => res.redirect(scriptUrl));

app.listen(PORT, () => {
    console.log(`Backend de vídeo rodando na porta ${PORT}`);
});
