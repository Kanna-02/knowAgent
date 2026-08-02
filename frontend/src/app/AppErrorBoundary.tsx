import { Button, Result } from "antd";
import { Home, RefreshCw } from "lucide-react";
import { Component, type ReactNode } from "react";

interface AppErrorBoundaryState {
  failed: boolean;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true };
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <Result
        status="error"
        title="页面加载失败"
        subTitle="当前页面遇到异常，未保存的输入可能仍保留在浏览器中。"
        extra={[
          <Button
            key="reload"
            type="primary"
            icon={<RefreshCw size={16} />}
            onClick={() => window.location.reload()}
          >
            重新加载
          </Button>,
          <Button key="home" icon={<Home size={16} />} onClick={() => window.location.assign("/")}>
            返回首页
          </Button>,
        ]}
      />
    );
  }
}
