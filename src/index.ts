import * as dotenv from 'dotenv';

dotenv.config();

import {createServer} from 'http';
import {setupExpressServer} from './setup';
import { env } from './config';
// import { startConsumer } from './broker/consumer';

function start(port: number) {
    const application = setupExpressServer([
        `http://localhost:${port}`,
        `http://127.0.0.1:${port}`,
    ]);
    const server = createServer(application as any);


    server.listen(port, () => console.log(`Application listening on port ${port}`))

    // startDB()
    // .then(() =>
    //     startConsumer()
    //     .then(() => server.listen(port, () => console.log(`Application listening on port ${port}`)))
    //     .catch(console.error)
    // ).catch((err) => {
    //     console.error(err);
    //     process.exit(1);
    // });
}

start(
  parseInt(env('APP_PORT', '1523'))
);
