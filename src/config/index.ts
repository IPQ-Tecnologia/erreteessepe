import { config as configDotenv } from 'dotenv';
import { resolve } from 'path';

const { parsed: parsedEnvData } = configDotenv({
  path: resolve(__dirname, '../../.env'),
  processEnv: process.env as any,
});

export const envData = (parsedEnvData || parsedEnvData ? Object.keys(parsedEnvData).length > 0 : null)
  ? parsedEnvData
  : process.env;

/**
 * Get enviroment value
 * @param {string} envName
 * @return {string | null}
 */
export function env<T = any>(envName: string, defaultValue: string | number | boolean | null = null): T {
  const parsed = envData as any;
  return parsed[envName] ?? defaultValue;
}
