import { ApiError } from "../api/client";

export interface UiError {
  message: string;
  requestId: string | null;
}

export function toUiError(error: unknown, fallbackMessage: string): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, requestId: error.requestId || null };
  }
  return { message: fallbackMessage, requestId: null };
}
