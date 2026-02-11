import cors from 'cors';
import morgan from 'morgan';
import routes from '@/src/protocols/http/routes';
import express, {Application} from 'express';
import {partial, compose, tryit, first} from 'radash';

import rtspRelay from 'rtsp-relay';
import expressWs, { Application as ExpressWsApplication } from 'express-ws';
import axios from 'axios';

function setupExpressInputConfigurations(application: Application): Application {
    application.use(express.json({limit: '15mb'}));
    application.use(express.urlencoded({extended: true}));
    return application;
}

function setupCors(allowedOrigins: readonly string[], application: Application): Application {
    return application.use(
        cors({
            credentials: true,
            origin: allowedOrigins as string[],
            methods: ['GET', 'POST'],
            allowedHeaders: ['Origin', 'Content-Type', 'Authorization', 'Accept', 'Cookie'],
        }),
    );
}

function setupExpressLoggers(application: Application): Application {
    return application.use(morgan('[:date[iso]] :method :url :status :res[content-length] - :response-time ms'));
}

function setupRouter(application: Application): Application {
    return application.use(routes);
}

function setupRelayRtsp(application: ExpressWsApplication): Application {
    console.log('entrei')
    expressWs(application);

    const { proxy, scriptUrl } = rtspRelay(application as unknown as Application);
    console.log('scriptUrl', scriptUrl);


    application.ws('/api/stream/:device', async (ws, req) => {
        const { device } = req.query;
        const start = new Date();
        start.setHours(start.getHours() - 24);
        // start.setSeconds(start.getSeconds() - 60);
        const end = new Date();


        const [err, response = { data: [] } ] = await tryit(axios.post)('http://localhost:63891/provider/dahua/dss/pro/8.4/video/playback', {
            device_id: device,
            start_date: start.toJSON(),
            end_date: end.toJSON()
        });

        if (err) return ws.close(ws.CLOSED);
        if (response.data.length === 0) {
            console.log('nenhuma url encontrada');
            return ws.close(ws.CLOSED);
        }
        const streamData = first(response.data, null);

        if (!streamData) return ws.close(ws.CLOSED);

        return proxy({ url: streamData['url'], transport: 'tcp' })(ws);
    });

    application.get('/', (req, res) => {
        res.send(`
        <canvas id='canvas'></canvas>
      
        <script src='${scriptUrl}'></script>
        <script>
          loadPlayer({
            url: 'ws://' + location.host + '/api/stream/' + 1000044,
            canvas: document.getElementById('canvas')
          });
        </script>
      `);
    });


    return application as unknown as Application;
}


export function setupExpressServer(allowedHosts: string[]): (Application: Application) => Application {
    return compose(
        setupRelayRtsp as never,
        setupRouter as never,
        partial(setupCors, allowedHosts) as never,
        setupExpressInputConfigurations as never,
        setupExpressLoggers as never,
        express()
    );
}
