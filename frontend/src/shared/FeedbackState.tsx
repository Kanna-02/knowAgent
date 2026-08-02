import { Alert, Button, Empty, Skeleton } from "antd";
import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import type { UiError } from "./uiError";

type FeedbackStateProps =
  | { status: "loading"; title: string }
  | { status: "empty"; title: string }
  | {
      status: "error";
      title: string;
      error: UiError;
      retryLabel: string;
      retrying: boolean;
      onRetry: () => void;
    };

export function FeedbackState(props: FeedbackStateProps): ReactNode {
  if (props.status === "loading") {
    return (
      <div className="feedback-state feedback-state-loading" aria-label={props.title}>
        <Skeleton active title paragraph={{ rows: 3 }} />
      </div>
    );
  }
  if (props.status === "empty") {
    return (
      <div className="feedback-state">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={props.title} />
      </div>
    );
  }
  const hasDescription = props.error.message !== props.title || Boolean(props.error.requestId);
  return (
    <Alert
      className="feedback-error"
      type="error"
      showIcon
      title={props.title}
      description={
        hasDescription ? (
          <div className="feedback-error-description">
            {props.error.message !== props.title ? <span>{props.error.message}</span> : null}
            {props.error.requestId ? (
              <span className="request-id">
                追踪 ID：<code>{props.error.requestId}</code>
              </span>
            ) : null}
          </div>
        ) : undefined
      }
      action={
        <Button
          size="small"
          icon={<RefreshCw size={15} />}
          aria-label={props.retryLabel}
          loading={props.retrying}
          disabled={props.retrying}
          onClick={props.onRetry}
        >
          重试
        </Button>
      }
    />
  );
}
