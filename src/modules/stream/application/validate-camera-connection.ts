import { spawn } from 'child_process';
import * as net from 'net';

export type CameraConnectionStatus =
  | { ok: true }
  | { ok: false; reason: 'unreachable' | 'auth_failed' | 'stream_error'; message: string };

const TCP_CHECK_TIMEOUT_MS = 3000;
const PROBE_TIMEOUT_SECONDS = 5;

/**
 * Quick TCP socket check to verify if the RTSP host:port is reachable.
 * This is much faster than ffprobe for detecting unreachable hosts.
 */
const checkTcpReachability = (rtspUrl: string): Promise<boolean> => {
  return new Promise((resolve) => {
    try {
      const parsedUrl = new URL(rtspUrl);
      const host = parsedUrl.hostname;
      const port = parseInt(parsedUrl.port, 10) || 554;

      const socket = new net.Socket();
      socket.setTimeout(TCP_CHECK_TIMEOUT_MS);

      socket.connect(port, host, () => {
        socket.destroy();
        resolve(true);
      });

      socket.on('error', () => {
        socket.destroy();
        resolve(false);
      });

      socket.on('timeout', () => {
        socket.destroy();
        resolve(false);
      });
    } catch {
      resolve(false);
    }
  });
};

export const validateCameraConnection = async (rtspUrl: string): Promise<CameraConnectionStatus> => {
  const isReachable = await checkTcpReachability(rtspUrl);
  console.log(`TCP reachability check for ${rtspUrl}: ${isReachable ? 'reachable' : 'unreachable'}`);

  if (!isReachable) {
    return { ok: false, reason: 'unreachable', message: 'Camera host is not reachable' };
  }

  return new Promise((resolve) => {
    const ffprobe = spawn('ffprobe', [
      '-v', 'error',
      '-rtsp_transport', 'tcp',
      '-timeout', String(PROBE_TIMEOUT_SECONDS * 1_000_000),
      '-i', rtspUrl,
    ]);

    let stderr = '';

    ffprobe.stderr.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    const timeout = setTimeout(() => {
      ffprobe.kill('SIGKILL');
      resolve({ ok: false, reason: 'unreachable', message: 'Connection timed out' });
    }, (PROBE_TIMEOUT_SECONDS + 2) * 1000);

    ffprobe.on('close', (code) => {
      clearTimeout(timeout);

      if (code === 0) {
        resolve({ ok: true });
        return;
      }

      const lowerStderr = stderr.toLowerCase();

      if (lowerStderr.includes('401') || lowerStderr.includes('unauthorized')) {
        resolve({ ok: false, reason: 'auth_failed', message: 'Invalid credentials' });
        return;
      }

      if (
        lowerStderr.includes('connection refused') ||
        lowerStderr.includes('network is unreachable') ||
        lowerStderr.includes('no route to host') ||
        lowerStderr.includes('connection timed out') ||
        lowerStderr.includes('timeout')
      ) {
        resolve({ ok: false, reason: 'unreachable', message: 'Camera is unreachable' });
        return;
      }

      resolve({
        ok: false,
        reason: 'stream_error',
        message: stderr.trim().slice(0, 200) || 'Unknown stream error',
      });
    });

    ffprobe.on('error', (err) => {
      clearTimeout(timeout);
      resolve({ ok: false, reason: 'stream_error', message: err.message });
    });
  });
};
