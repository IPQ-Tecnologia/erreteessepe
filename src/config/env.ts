import dotenv from 'dotenv';

dotenv.config();

const readEnv = (name: string): string | undefined => process.env[name];

const optionalString = (name: string): string | undefined => {
  const value = readEnv(name);
  return value && value.trim().length > 0 ? value : undefined;
};

const string = (name: string, defaultValue: string): string => {
  return optionalString(name) ?? defaultValue;
};

const number = (name: string, defaultValue: number): number => {
  const rawValue = readEnv(name);
  if (!rawValue) {
    return defaultValue;
  }

  const parsedValue = Number(rawValue);
  return Number.isFinite(parsedValue) ? parsedValue : defaultValue;
};

export const env = {
  optionalString,
  string,
  number,
};
