import { env } from './config/env';
import { createServer } from './server/create-server';

const port = env.number('APP_PORT', 1523);
const application = createServer();

application.listen(port, () => {
  console.log(`backend running on port ${port}`);
});
