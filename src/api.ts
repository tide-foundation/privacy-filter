export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/service/${path}`, {
    ...init, credentials: 'same-origin', cache: 'no-store',
  });
  const data = await response.json();
  if (!response.ok) {
    throw new ApiError(typeof data.detail === 'string' ? data.detail : 'The request could not be completed.', response.status);
  }
  return data as T;
}

export function isAborted(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}
